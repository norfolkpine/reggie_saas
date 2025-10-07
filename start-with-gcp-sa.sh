#!/bin/bash

# Script to start production services with GCP_SA_KEY from GitHub secrets
# This script writes the GCP_SA_KEY environment variable to a file that the Cloud SQL proxy can use

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting production services with GCP_SA_KEY...${NC}"

# Check if GCP_SA_KEY is set
if [ -z "$GCP_SA_KEY" ]; then
    echo -e "${RED}Error: GCP_SA_KEY environment variable is not set${NC}"
    echo -e "${YELLOW}Make sure to set GCP_SA_KEY with your service account JSON${NC}"
    exit 1
fi

# Create credentials file for Cloud SQL proxy
echo -e "${YELLOW}Creating credentials file for Cloud SQL proxy...${NC}"
echo "$GCP_SA_KEY" > /tmp/gcp-credentials.json

# Validate the JSON
if ! python3 -m json.tool /tmp/gcp-credentials.json > /dev/null 2>&1; then
    echo -e "${RED}Error: GCP_SA_KEY contains invalid JSON${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Credentials file created successfully${NC}"

# Start the services
echo -e "${YELLOW}Starting production services...${NC}"
docker-compose -f docker-compose.prod.yml up -d

echo -e "${GREEN}✓ Production services started successfully${NC}"
echo -e "${YELLOW}Cloud SQL proxy should be available on localhost:5432${NC}"
