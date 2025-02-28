# Copyright 2025 The HuggingFace Team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re
from dataclasses import dataclass, field

from datasets import load_dataset

from latex2sympy2_extended import NormalizationConfig
from math_verify import LatexExtractionConfig, parse, verify

from trl_x.grpox_config import GRPOConfig
from trl_x.grpox_trainer import GRPOTrainer

from optimum.neuron import (
    NeuronModelForCausalLM as AutoModelForCausalLM,
    NeuronTrainer as Trainer,
    NeuronModelForSequenceClassification as AutoModelForSequenceClassification
)

import torch_xla.core.xla_model as xm

def accuracy_reward(completions, solution, **kwargs):
    """Reward function that checks if the completion is the same as the ground truth."""
    contents = [completion[0]["content"] for completion in completions]
    rewards = []
    for content, sol in zip(contents, solution):
        gold_parsed = parse(sol, extraction_mode="first_match", extraction_config=[LatexExtractionConfig()])
        if len(gold_parsed) != 0:
            # We require the answer to be provided in correct latex (no malformed operators)
            answer_parsed = parse(
                content,
                extraction_config=[
                    LatexExtractionConfig(
                        normalization_config=NormalizationConfig(
                            nits=False,
                            malformed_operators=False,
                            basic_latex=True,
                            equations=True,
                            boxed=True,
                            units=True,
                        ),
                        # Ensures that boxed is tried first
                        boxed_match_priority=0,
                        try_extract_without_anchor=False,
                    )
                ],
                extraction_mode="first_match",
            )
            # Reward 1 if the content is the same as the ground truth, 0 otherwise
            reward = float(verify(answer_parsed, gold_parsed))
        else:
            # If the gold solution is not parseable, we reward 1 to skip this example
            reward = 1.0
            print("Failed to parse gold solution: ", sol)
        rewards.append(reward)

    return rewards


def format_reward(completions, **kwargs):
    """Reward function that checks if the completion has a specific format."""
    pattern = r"^<think>.*?</think><answer>.*?</answer>$"
    completion_contents = [completion[0]["content"] for completion in completions]
    matches = [re.match(pattern, content) for content in completion_contents]
    return [1.0 if match else 0.0 for match in matches]


reward_funcs_registry = {
    "accuracy": accuracy_reward,
    "format": format_reward,
}

SYSTEM_PROMPT = (
    "A conversation between User and Assistant. The user asks a question, and the Assistant solves it. The assistant "
    "first thinks about the reasoning process in the mind and then provides the user with the answer. The reasoning "
    "process and answer are enclosed within <think> </think> and <answer> </answer> tags, respectively, i.e., "
    "<think> reasoning process here </think><answer> answer here </answer>"
)

def main(compiled_model_path, dataset_name, model_output_dir, reward_types, training_args):
    
    # Get reward functions
    reward_funcs = [reward_funcs_registry[func] for func in reward_types]

    # Load the dataset
    dataset = load_dataset(dataset_name)

    # Format into conversation
    def make_conversation(example):
        return {
            "prompt": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": example["problem"]},
            ],
        }

    dataset = dataset.map(make_conversation)

     # Initialize the GRPO trainer
    trainer = GRPOTrainer(
        model=compiled_model_path,
        reward_funcs=reward_funcs,
        train_dataset=dataset['train'],
        eval_dataset=dataset['test'],
    )

    # Train and push the model to the Hub
    trainer.train()

    trainer.save_model(model_output_dir)

if __name__ == "__main__":

    dataset_name = 'AI-MO/NuminaMath-TIR'

    compiled_model_path = '/home/ubuntu/models/traced_qwen'

    model_output_dir = '/home/ubuntu/models/grpo_qwen'
    
    reward_types = ['accuracy', 'format']

    # training_args = {"model_init_kwargs":{'max_prompt_length':256,
    #                 'per_device_train_batch_size': 1,
    #                 'gradient_accumulation_steps': 16,
    #                 'logging_steps': 10,
    #                 'data_type':'bf16'}}
                    
    main(compiled_model_path, dataset_name, model_output_dir, reward_types, training_args = {})


