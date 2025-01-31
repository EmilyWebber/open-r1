#!/bin/bash

optimum-cli export neuron \
  --model deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B \
  --batch_size 1 \
  --sequence_length 4096 \
  --num_cores 2 \
  --auto_cast_type bf16 \
  /home/ubuntu/models/traced_qwen