#!/bin/bash

# Script to delete all images except the most recent one for each service
# This is safer than deleting all except 'latest' since there are no 'latest' tags

set -e

# Configuration
PROJECT_ID="bh-opie"
REGION="australia-southeast1"
REPOSITORY="containers"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🗑️  Starting image cleanup (keeping only most recent)...${NC}"

# Function to cleanup images for a specific service
cleanup_service() {
    local service_name=$1
    local full_image_path="australia-southeast1-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${service_name}"
    
    echo -e "${YELLOW}📦 Cleaning up images for: ${service_name}${NC}"
    
    # Get list of all versions, sorted by creation time (newest first)
    local versions=$(gcloud artifacts docker images list "${full_image_path}" \
        --sort-by="~CREATE_TIME" \
        --format="value(version)" 2>/dev/null || echo "")
    
    if [ -z "$versions" ]; then
        echo -e "${YELLOW}  ⚠️  No images found for ${service_name}${NC}"
        return
    fi
    
    # Count total versions
    local total_versions=$(echo "$versions" | wc -l)
    echo -e "  📊 Found ${total_versions} versions"
    
    if [ "$total_versions" -le 1 ]; then
        echo -e "  ✅ No cleanup needed (only ${total_versions} version)"
        return
    fi
    
    # Keep only the first (most recent) version, delete the rest
    local versions_to_delete=$(echo "$versions" | tail -n +2)
    local delete_count=$(echo "$versions_to_delete" | wc -l)
    local keep_version=$(echo "$versions" | head -1)
    
    echo -e "  🔒 Keeping most recent: ${keep_version}"
    echo -e "  🗑️  Will delete ${delete_count} old versions"
    
    # Delete old versions
    echo "$versions_to_delete" | while read -r version; do
        if [ -n "$version" ]; then
            echo -e "    🗑️  Deleting ${service_name}:${version}"
            gcloud artifacts docker images delete "${full_image_path}:${version}" --quiet || true
        fi
    done
    
    echo -e "  ✅ Cleanup completed for ${service_name}"
}

# List of services to cleanup
SERVICES=(
    "opie-web"
    "opie-y-provider"
)

# Cleanup each service
for service in "${SERVICES[@]}"; do
    cleanup_service "$service"
done

echo -e "${GREEN}🎉 Image cleanup completed!${NC}"

# Show remaining images
echo -e "\n${YELLOW}📊 Remaining images:${NC}"
for service in "${SERVICES[@]}"; do
    echo -e "\n${service}:"
    gcloud artifacts docker images list "australia-southeast1-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${service}" \
        --format="table(version,createTime)" --sort-by="~CREATE_TIME" 2>/dev/null || echo "No images found"
done
