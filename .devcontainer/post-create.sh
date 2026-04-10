#!/bin/bash
set -e

# Fix SSH and AWS permissions
chmod 700 /home/vscode/.ssh
chmod 600 /home/vscode/.ssh/id_* 2>/dev/null || true
chmod 700 /home/vscode/.aws 2>/dev/null || true

# Install Sapling SCM
ARCH=$(uname -m | sed 's/x86_64/x64/;s/aarch64/arm64/')
rm -rf ~/.local/share/sapling
mkdir -p ~/.local/share/sapling
curl -L "https://github.com/facebook/sapling/releases/download/0.2.20260317-201835%2B0234c21f/sapling-0.2.20260317-201835%2B0234c21f-linux-${ARCH}.tar.xz" \
  | tar xJf - -C ~/.local/share/sapling
grep -q 'sapling' ~/.bashrc || echo 'export PATH="$HOME/.local/share/sapling:$PATH"' >> ~/.bashrc

# Install kubectl
ARCH=$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/${ARCH}/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/

# Install eksctl
ARCH=$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')
curl -sLO "https://github.com/eksctl-io/eksctl/releases/latest/download/eksctl_Linux_${ARCH}.tar.gz"
tar xzf eksctl_Linux_${ARCH}.tar.gz
chmod +x eksctl
sudo mv eksctl /usr/local/bin/
rm -f eksctl_Linux_${ARCH}.tar.gz

# Install Claude Code
curl -fsSL https://claude.ai/install.sh | bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

# Patch kubeconfig for Docker Desktop K8s access from inside container
# kubernetes.docker.internal resolves to the host AND is in the API server's TLS cert SANs
if [ -f /home/vscode/.kube/config ]; then
  sed -i 's|https://127\.0\.0\.1:6443|https://kubernetes.docker.internal:6443|g' /home/vscode/.kube/config
fi


### 1. Create EKS
# eksctl create cluster \
#   --name practice-cluster \
#   --region us-west-2 \
#   --nodegroup-name practice-nodes \
#   --node-type t3.small \
#   --nodes 2 \
#   --nodes-min 1 \
#   --nodes-max 3

### 2. Verify
# kubectl get nodes
# kubectl get pods --all-namespaces

### 3. Deploy something to play with
# kubectl create deployment nginx --image=nginx
# kubectl expose deployment nginx --port=80 --type=LoadBalancer
# kubectl get services -w

### 4. Clean up when done
# eksctl delete cluster --name practice-cluster --region us-west-2
