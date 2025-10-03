#!/bin/bash

# Script to test Cloud SQL proxy with GCP_SA_KEY
# This script reads the service account key and exports it as GCP_SA_KEY

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Setting up Cloud SQL proxy test with GCP_SA_KEY...${NC}"

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo -e "${RED}Error: .env file not found. Please create one with required variables.${NC}"
    exit 1
fi

# Load environment variables
source .env

# Check if PROJECT_ID is set
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}Error: PROJECT_ID not set in .env file${NC}"
    exit 1
fi

# Check if service account file exists
SA_FILE=".gcp/creds/bh-opie/github-actions.json"
if [ ! -f "$SA_FILE" ]; then
    echo -e "${RED}Error: Service account file not found at $SA_FILE${NC}"
    exit 1
fi

# Verify the service account file exists and is readable
echo -e "${YELLOW}Using service account file: $SA_FILE...${NC}"

# Test if the JSON is valid
if ! python3 -m json.tool "$SA_FILE" > /dev/null 2>&1; then
    echo -e "${RED}Error: Service account file contains invalid JSON${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Service account file is valid${NC}"
echo -e "${YELLOW}Starting Cloud SQL proxy on port 5433...${NC}"

# Start the Cloud SQL proxy
docker-compose -f docker-compose.cloudsql-test.yml up --build

echo -e "${GREEN}Cloud SQL proxy test completed${NC}"
echo -e "${YELLOW}The proxy is available at localhost:5433${NC}"
