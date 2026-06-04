#!/usr/bin/env bash
# Copyright 2026 Muhammad Waleed & Areeba
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

set -e

NAMESPACE="taafi-system"

echo "=== Taafi.ai Secret Creation Helper (Alibaba ACK) ==="

# Create namespace if it does not exist
if ! kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
    echo "Creating namespace: $NAMESPACE..."
    kubectl create namespace "$NAMESPACE"
else
    echo "Namespace '$NAMESPACE' already exists."
fi

# Request DB DSN
read -rp "Enter PostgreSQL DB DSN [default: postgresql://taafi:taafi_pass@postgres-service:5432/taafi]: " DB_DSN
DB_DSN=${DB_DSN:-"postgresql://taafi:taafi_pass@postgres-service:5432/taafi"}

# Request DashScope key
read -rp "Enter DASHSCOPE_API_KEY for Qwen-max: " DASHSCOPE_KEY

# Delete existing secret if it exists
if kubectl get secret taafi-secret -n "$NAMESPACE" >/dev/null 2>&1; then
    echo "Recreating taafi-secret..."
    kubectl delete secret taafi-secret -n "$NAMESPACE"
fi

# Create Kubernetes Secret
kubectl create secret generic taafi-secret -n "$NAMESPACE" \
  --from-literal=TAAFI_DB_URL="$DB_DSN" \
  --from-literal=DASHSCOPE_API_KEY="$DASHSCOPE_KEY"

echo "============================================="
echo "✅ Secrets created successfully in namespace '$NAMESPACE'."
echo "Database DSN: $DB_DSN"
echo "Qwen-max API key has been registered."
echo "============================================="
