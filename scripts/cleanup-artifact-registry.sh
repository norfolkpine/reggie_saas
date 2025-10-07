#!/bin/bash

# Artifact Registry Image Cleanup Script
# This script removes old Docker images from GCP Artifact Registry to prevent storage bloat

set -e

# Configuration
PROJECT_ID="bh-opie"
REGION="australia-southeast1"
REPOSITORY="containers"

# Retention policies
KEEP_LATEST_VERSIONS=10     # Keep last 10 versions (for quick rollbacks)
KEEP_STABLE_VERSIONS=5      # Keep 5 stable versions (tagged with v*.*.*)
KEEP_MAIN_BRANCH_VERSIONS=7 # Keep 7 versions from main branch
KEEP_DEV_BRANCH_VERSIONS=3  # Keep 3 versions from dev branch

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🧹 Starting Artifact Registry cleanup...${NC}"

# Function to cleanup images for a specific image name with smart retention
cleanup_image() {
    local image_name=$1
    local full_image_path="australia-southeast1-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${image_name}"
    
    echo -e "${YELLOW}📦 Cleaning up images for: ${image_name}${NC}"
    
    # Get detailed list of all versions with metadata
    local versions_info=$(gcloud artifacts docker images list "${full_image_path}" \
        --sort-by="~CREATE_TIME" \
        --format="table(version,createTime,tags)" 2>/dev/null || echo "")
    
    if [ -z "$versions_info" ]; then
        echo -e "${YELLOW}  ⚠️  No images found for ${image_name}${NC}"
        return
    fi
    
    # Extract just the versions
    local versions=$(echo "$versions_info" | tail -n +2 | awk '{print $1}')
    local total_versions=$(echo "$versions" | wc -l)
    echo -e "  📊 Found ${total_versions} versions"
    
    if [ "$total_versions" -le "$KEEP_LATEST_VERSIONS" ]; then
        echo -e "  ✅ No cleanup needed (${total_versions} <= ${KEEP_LATEST_VERSIONS})"
        return
    fi
    
    # Smart cleanup strategy
    local versions_to_keep=""
    local versions_to_delete=""
    
    # 1. Always keep 'latest' tag
    local latest_version=$(echo "$versions_info" | grep -E "latest" | awk '{print $1}' | head -1)
    if [ -n "$latest_version" ]; then
        versions_to_keep="$latest_version"
        echo -e "  🔒 Keeping latest: ${latest_version}"
    fi
    
    # 2. Keep stable versions (v*.*.* pattern)
    local stable_versions=$(echo "$versions_info" | grep -E "v[0-9]+\.[0-9]+\.[0-9]+" | awk '{print $1}' | head -${KEEP_STABLE_VERSIONS})
    if [ -n "$stable_versions" ]; then
        versions_to_keep="$versions_to_keep $stable_versions"
        echo -e "  🔒 Keeping stable versions: $(echo $stable_versions | tr '\n' ' ')"
    fi
    
    # 3. Keep recent versions (by creation time)
    local recent_versions=$(echo "$versions" | head -${KEEP_LATEST_VERSIONS})
    versions_to_keep="$versions_to_keep $recent_versions"
    
    # Remove duplicates and create final keep list
    versions_to_keep=$(echo "$versions_to_keep" | tr ' ' '\n' | sort -u | tr '\n' ' ')
    
    # Find versions to delete (not in keep list)
    versions_to_delete=""
    for version in $versions; do
        if ! echo "$versions_to_keep" | grep -q "$version"; then
            versions_to_delete="$versions_to_delete $version"
        fi
    done
    
    local delete_count=$(echo "$versions_to_delete" | wc -w)
    local keep_count=$(echo "$versions_to_keep" | wc -w)
    
    echo -e "  📈 Will keep ${keep_count} versions, delete ${delete_count} versions"
    
    # Delete old versions
    for version in $versions_to_delete; do
        if [ -n "$version" ]; then
            echo -e "    🗑️  Deleting ${image_name}:${version}"
            gcloud artifacts docker images delete "${full_image_path}:${version}" --quiet || true
        fi
    done
    
    echo -e "  ✅ Cleanup completed for ${image_name}"
}

# List of images to cleanup
IMAGES=(
    "opie-web"
    "opie-y-provider"
    "llamaindex-ingestion"
)

# Cleanup each image
for image in "${IMAGES[@]}"; do
    cleanup_image "$image"
done

echo -e "${GREEN}🎉 Artifact Registry cleanup completed!${NC}"

# Show current storage usage
echo -e "\n${YELLOW}📊 Current storage usage:${NC}"
gcloud artifacts repositories describe "${REPOSITORY}" \
    --location="${REGION}" \
    --project="${PROJECT_ID}" \
    --format="table(name,sizeBytes)" 2>/dev/null || echo "Could not retrieve storage info"
