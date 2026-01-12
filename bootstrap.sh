#!/bin/bash

# Bxthre3 Distributed Execution System - Bootstrap Script
# This script sets up the complete Bxthre3 environment

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Repository configuration
GITHUB_REPO="bxthre3/bxthre3"
GITHUB_RAW="https://raw.githubusercontent.com/${GITHUB_REPO}/main"
LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Bxthre3 Distributed Execution System  ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Detect environment
detect_environment() {
    echo -e "${GREEN}Detecting environment...${NC}"
    
    if [ -d "/data/data/com.termux" ]; then
        ENVIRONMENT="termux"
        echo -e "${GREEN}Detected: Android Termux${NC}"
    elif [ -f "/proc/1/cgroup" ] && grep -q "docker\|lxc" /proc/1/cgroup 2>/dev/null; then
        ENVIRONMENT="container"
        echo -e "${GREEN}Detected: Container/VM${NC}"
    elif [ -f "/sys/hypervisor/uuid" ] && grep -q "ec2" /sys/hypervisor/uuid 2>/dev/null; then
        ENVIRONMENT="aws"
        echo -e "${GREEN}Detected: AWS EC2${NC}"
    elif [ -f "/var/lib/cloud/data/instance-id" ] 2>/dev/null; then
        ENVIRONMENT="cloud"
        echo -e "${GREEN}Detected: Cloud Instance${NC}"
    else
        ENVIRONMENT="linux"
        echo -e "${GREEN}Detected: Linux System${NC}"
    fi
}

# Install dependencies
install_dependencies() {
    echo -e "${GREEN}Installing dependencies...${NC}"
    
    case "$ENVIRONMENT" in
        termux)
            pkg update -y
            pkg install -y git python cmake clang curl
            ;;
        linux|container|aws|cloud)
            if command -v apt-get &> /dev/null; then
                sudo apt-get update -y
                sudo apt-get install -y git python3 python3-pip cmake clang curl build-essential
            elif command -v yum &> /dev/null; then
                sudo yum install -y git python3 python3-pip cmake clang curl make gcc gcc-c++
            elif command -v apk &> /dev/null; then
                sudo apk add --no-cache git python3 py3-pip cmake clang curl make gcc g++
            else
                echo -e "${RED}Unknown package manager. Please install git, python3, cmake, clang, curl manually.${NC}"
                exit 1
            fi
            ;;
    esac
    
    # Install Python dependencies
    echo -e "${GREEN}Installing Python packages...${NC}"
    pip3 install --user -q pyyaml requests 2>/dev/null || pip3 install -q pyyaml requests
}

# Download or build Wasm3 runtime
setup_wasm3() {
    echo -e "${GREEN}Setting up Wasm3 runtime...${NC}"
    
    mkdir -p "$LOCAL_DIR/wasm_modules"
    cd "$LOCAL_DIR/wasm_modules"
    
    # Check if m3 directory already exists
    if [ -d "m3" ] && [ -f "m3/build/wasm3" ]; then
        echo -e "${GREEN}Wasm3 already built. Skipping...${NC}"
        cd "$LOCAL_DIR"
        return
    fi
    
    # Try to download pre-built wasm3
    if curl -L -o wasm3 "https://github.com/wasm3/wasm3/releases/download/v0.5.0/wasm3-linux-x64" 2>/dev/null; then
        chmod +x wasm3
        mkdir -p m3
        mv wasm3 m3/
        echo -e "${GREEN}Downloaded pre-built wasm3${NC}"
    else
        echo -e "${YELLOW}Pre-built wasm3 not available, building from source...${NC}"
        
        # Clone and build wasm3
        rm -rf m3
        git clone --depth 1 --branch v0.5.0 https://github.com/wasm3/wasm3.git m3
        
        cd m3
        
        case "$ENVIRONMENT" in
            termux)
                # Termux needs special handling
                mkdir -p build
                cd build
                cmake .. -DCMAKE_BUILD_TYPE=Release
                make -j$(nproc 2>/dev/null || echo 2)
                ;;
            *)
                # Standard Linux build
                make -j$(nproc 2>/dev/null || echo 2)
                ;;
        esac
        
        cd "$LOCAL_DIR"
    fi
    
    # Verify wasm3 is available
    if [ -f "$LOCAL_DIR/wasm_modules/m3/wasm3" ] || [ -f "$LOCAL_DIR/wasm_modules/m3/build/wasm3" ]; then
        echo -e "${GREEN}Wasm3 runtime setup complete${NC}"
    else
        echo -e "${YELLOW}Warning: wasm3 binary not found. Will try alternative paths...${NC}"
    fi
}

# Download files from GitHub
download_file() {
    local remote_path=$1
    local local_path=$2
    
    echo -e "Downloading: $remote_path"
    if curl -fsSL "${GITHUB_RAW}/${remote_path}" -o "$local_path"; then
        echo -e "${GREEN}✓${NC} $remote_path"
        return 0
    else
        echo -e "${RED}✗${NC} $remote_path (not found or download failed)"
        return 1
    fi
}

# Download all system files from GitHub
download_system_files() {
    echo -e "${GREEN}Downloading system files from GitHub...${NC}"
    
    # Create directories
    mkdir -p "$LOCAL_DIR/wasm_modules"
    mkdir -p "$LOCAL_DIR/dags"
    
    # Download Python scripts
    download_file "bxthre3_ui.py" "$LOCAL_DIR/bxthre3_ui.py"
    download_file "bxthre3_controller.py" "$LOCAL_DIR/bxthre3_controller.py"
    download_file "bxthre3_host.py" "$LOCAL_DIR/bxthre3_host.py"
    download_file "bxthre3_node_manager.py" "$LOCAL_DIR/bxthre3_node_manager.py"
    
    # Download WASM modules
    download_file "wasm_modules/init.wasm" "$LOCAL_DIR/wasm_modules/init.wasm"
    download_file "wasm_modules/greet_1.wasm" "$LOCAL_DIR/wasm_modules/greet_1.wasm"
    download_file "wasm_modules/greet_2.wasm" "$LOCAL_DIR/wasm_modules/greet_2.wasm"
    download_file "wasm_modules/aggregate.wasm" "$LOCAL_DIR/wasm_modules/aggregate.wasm"
    
    # Download DAG manifests
    download_file "dags/hello_fanout.yaml" "$LOCAL_DIR/dags/hello_fanout.yaml"
}

# Get device ID
get_device_id() {
    local device_id
    
    if [ -f "/etc/machine-id" ]; then
        device_id=$(cat /etc/machine-id | cut -c1-8)
    elif command -v hostname &> /dev/null; then
        device_id=$(hostname | md5sum | cut -c1-8)
    else
        device_id="dev-$(date +%s)"
    fi
    
    echo "$device_id"
}

# Discover Controller IP
discover_controller() {
    echo -e "${GREEN}Discovering Controller IP...${NC}"
    
    local controller_ip=""
    
    # Try environment variable first
    if [ -n "$BXTHRE3_CONTROLLER" ]; then
        controller_ip="$BXTHRE3_CONTROLLER"
        echo -e "${GREEN}Found Controller IP from environment: $controller_ip${NC}"
    else
        # Prompt user
        read -p "Enter Controller IP address (or leave blank for localhost): " controller_ip
        controller_ip=${controller_ip:-"127.0.0.1"}
    fi
    
    echo "$controller_ip"
}

# Prompt for role selection
prompt_role() {
    echo ""
    echo -e "${BLUE}Select role(s) to launch:${NC}"
    echo "1) UI Node"
    echo "2) Controller + Node Manager"
    echo "3) Node Manager only"
    echo "4) Host Node only (for testing)"
    echo "5) All components (Controller, Node Manager, UI)"
    echo ""
    
    read -p "Enter choice (1-5): " choice
    
    case "$choice" in
        1) echo "ui";;
        2) echo "controller_manager";;
        3) echo "manager";;
        4) echo "host";;
        5) echo "all";;
        *) 
            echo -e "${RED}Invalid choice. Defaulting to UI Node.${NC}"
            echo "ui"
            ;;
    esac
}

# Prompt for RAM per logical node
prompt_ram() {
    echo ""
    read -p "Enter RAM per logical node in MB (default 128): " ram_input
    local ram=${ram_input:-128}
    
    # Validate input
    if ! [[ "$ram" =~ ^[0-9]+$ ]] || [ "$ram" -lt 32 ] || [ "$ram" -gt 4096 ]; then
        echo -e "${YELLOW}Invalid RAM value. Using default 128MB.${NC}"
        ram=128
    fi
    
    echo "$ram"
}

# Launch UI Node
launch_ui() {
    local controller_ip=$1
    echo -e "${GREEN}Launching UI Node...${NC}"
    echo "Connecting to Controller: $controller_ip"
    
    cd "$LOCAL_DIR"
    python3 bxthre3_ui.py --controller "$controller_ip"
}

# Launch Controller
launch_controller() {
    echo -e "${GREEN}Launching Controller Node...${NC}"
    
    cd "$LOCAL_DIR"
    python3 bxthre3_controller.py
}

# Launch Node Manager
launch_manager() {
    local ram_per_node=$1
    echo -e "${GREEN}Launching Node Manager (RAM per node: ${ram_per_node}MB)...${NC}"
    
    cd "$LOCAL_DIR"
    python3 bxthre3_node_manager.py --ram-per-node "$ram_per_node"
}

# Launch Host Node
launch_host() {
    local ram_limit=$1
    local node_id=$2
    echo -e "${GREEN}Launching Host Node (RAM: ${ram_limit}MB, ID: ${node_id})...${NC}"
    
    cd "$LOCAL_DIR"
    python3 bxthre3_host.py --ram-limit "$ram_limit" --node-id "$node_id"
}

# Main execution
main() {
    detect_environment
    
    # Check if running in workspace/local development mode
    if [ -f "$LOCAL_DIR/bxthre3_ui.py" ] && [ "$1" != "--force-download" ]; then
        echo -e "${GREEN}Local development mode detected. Skipping downloads.${NC}"
    else
        install_dependencies
        setup_wasm3
        
        # Try to download from GitHub, but don't fail if not available
        echo -e "${YELLOW}Attempting to download from GitHub (may fail if repository doesn't exist yet)...${NC}"
        download_system_files || echo -e "${YELLOW}GitHub download failed (expected for new repository). Using local files.${NC}"
    fi
    
    # Get configuration
    local role=$(prompt_role)
    local ram_per_node=$(prompt_ram)
    local device_id=$(get_device_id)
    local controller_ip="127.0.0.1"
    
    echo ""
    echo -e "${BLUE}Configuration:${NC}"
    echo "  Role: $role"
    echo "  RAM per logical node: ${ram_per_node}MB"
    echo "  Device ID: $device_id"
    echo ""
    
    # Launch based on role selection
    case "$role" in
        ui)
            controller_ip=$(discover_controller)
            launch_ui "$controller_ip"
            ;;
        controller_manager)
            launch_controller &
            sleep 2
            launch_manager "$ram_per_node"
            ;;
        manager)
            controller_ip=$(discover_controller)
            export BXTHRE3_CONTROLLER="$controller_ip"
            launch_manager "$ram_per_node"
            ;;
        host)
            controller_ip=$(discover_controller)
            export BXTHRE3_CONTROLLER="$controller_ip"
            launch_host "$ram_per_node" "${device_id}-0"
            ;;
        all)
            launch_controller &
            CONTROLLER_PID=$!
            sleep 2
            controller_ip="127.0.0.1"
            launch_manager "$ram_per_node" &
            sleep 3
            launch_ui "$controller_ip"
            ;;
    esac
}

# Run main function
main "$@"