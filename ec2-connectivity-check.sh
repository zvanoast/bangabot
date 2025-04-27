#!/bin/bash

# EC2 Connectivity Troubleshooting Script
# This script checks connectivity to your EC2 instance and helps diagnose issues

# Set the target EC2 instance - replace with your instance IP
EC2_HOST="34.227.47.206"
EC2_PORT=22

echo "=== EC2 Connectivity Check ==="
echo "Target: $EC2_HOST:$EC2_PORT"
echo ""

# Check if host is reachable
echo "1. Ping test to check if host is reachable:"
ping -c 4 $EC2_HOST
echo ""

# Check if port 22 is open
echo "2. Port check (SSH - port 22):"
if command -v nc &> /dev/null; then
    nc -zv $EC2_HOST 22 -w 5
elif command -v telnet &> /dev/null; then
    echo "Using telnet to check port..."
    echo quit | telnet $EC2_HOST 22
else
    echo "Neither nc nor telnet found. Install one of them to check port connectivity."
fi
echo ""

# Check SSH connectivity (if key file is provided)
if [ -n "$1" ]; then
    KEY_FILE="$1"
    echo "3. Testing SSH connection with key file: $KEY_FILE"
    ssh -i "$KEY_FILE" -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o BatchMode=yes ubuntu@$EC2_HOST "echo SSH connection successful!"
else
    echo "3. SSH connection test skipped - no key file provided."
    echo "   To test SSH connection, run: $0 /path/to/your/key.pem"
fi
echo ""

# Check AWS Security Group settings
echo "4. AWS Security Group check:"
echo "   Make sure your EC2 security group allows inbound traffic on port 22 from the GitHub Actions IP range."
echo "   GitHub Actions uses dynamic IP addresses, so you may need to allow all IPs (0.0.0.0/0) for SSH."
echo ""

# Summary
echo "=== Summary and Next Steps ==="
echo "If all tests passed, your EC2 instance is reachable."
echo "If any tests failed, check the following:"
echo " - Is the EC2 instance running?"
echo " - Is the security group configured to allow SSH from GitHub Actions IPs?"
echo " - Is the SSH key correct and properly formatted?"
echo " - Is there a firewall blocking the connection?"
echo " - Does the user (ubuntu) have the correct permissions?"
echo ""
echo "For GitHub Actions, make sure these secrets are correctly set:"
echo " - EC2_SSH_PRIVATE_KEY: The private key content (not path)"
echo " - EC2_REMOTE_HOST: $EC2_HOST (should match your instance IP)"
echo " - EC2_REMOTE_USER: ubuntu (or your instance username)"