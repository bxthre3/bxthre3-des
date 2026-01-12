# Bxthre3 Distributed Execution System

A distributed task execution system built with Python and WebAssembly that dynamically scales compute nodes based on available RAM.

## Features

- **Dynamic Multi-Node Scaling**: Automatically spawn logical nodes based on available RAM
- **WASM-Based Execution**: Run tasks using WebAssembly modules via Wasm3 runtime
- **DAG Orchestration**: Submit and monitor complex task dependencies
- **Cross-Platform**: Supports Linux VMs, cloud instances, and Android Termux
- **Auto-Discovery**: Devices automatically discover and connect to the Controller
- **Live Monitoring**: Real-time UI for task execution monitoring

## Architecture

### Components

1. **UI Node**: User interface for submitting DAGs and monitoring execution
2. **Controller Node**: Central coordinator that schedules tasks to available nodes
3. **Host Node**: Executes tasks using WASM modules
4. **Node Manager**: Manages multiple logical nodes based on available RAM

### Directory Structure

```
bxthre3/
├── bootstrap.sh              # Setup and launch script
├── bxthre3_ui.py            # UI Node
├── bxthre3_controller.py    # Controller Node
├── bxthre3_host.py          # Host Node
├── bxthre3_node_manager.py  # Node Manager
├── wasm_modules/            # WASM runtime and modules
│   ├── m3/                  # Wasm3 runtime
│   ├── init.wasm
│   ├── greet_1.wasm
│   ├── greet_2.wasm
│   └── aggregate.wasm
├── dags/                    # DAG configurations
│   └── hello_fanout.yaml
└── logs/                    # Log files
```

## Quick Start

### 1. Bootstrap the System

```bash
cd bxthre3
chmod +x bootstrap.sh
./bootstrap.sh
```

The bootstrap script will:
- Detect your environment (Linux, cloud, or Termux)
- Install dependencies (git, python3, cmake, clang)
- Download/build the Wasm3 runtime
- Download system files from GitHub
- Prompt for role selection

### 2. Choose Your Role

When running bootstrap, select one of the following:

1. **UI Node** - Submit and monitor DAGs
2. **Controller + Node Manager** - Run both controller and node manager
3. **Node Manager only** - Connect to existing controller
4. **Host Node only** - Single host instance for testing
5. **All components** - Run everything locally

### 3. Configure RAM per Node

The bootstrap will ask for RAM per logical node (default: 128MB). The Node Manager will automatically calculate how many nodes can run based on available RAM.

## Manual Launch

### Controller Node

```bash
python3 bxthre3_controller.py --host 0.0.0.0 --port 5000
```

### Node Manager

```bash
python3 bxthre3_node_manager.py --controller 127.0.0.1 --ram-per-node 128
```

### UI Node

```bash
python3 bxthre3_ui.py --controller 127.0.0.1
```

### Host Node (standalone)

```bash
python3 bxthre3_host.py --controller 127.0.0.1 --ram-limit 128 --node-id host-001
```

## Submitting DAGs

DAGs are defined in YAML format:

```yaml
name: "My DAG"
tasks:
  - id: "task1"
    module: "module1.wasm"
    inputs: ["input1", "input2"]
    depends_on: []

  - id: "task2"
    module: "module2.wasm"
    inputs: ["output_of_task1"]
    depends_on: ["task1"]
```

Submit a DAG via the UI:

1. Start the UI Node
2. Select "Submit DAG from file"
3. Enter the path to your YAML file

## WASM Modules

The system uses Wasm3 runtime to execute WebAssembly modules. Modules should be compiled to WASM format and placed in the `wasm_modules/` directory.

### Creating WASM Modules

Compile your code to WASM using:

- **C**: `clang --target=wasm32 --sysroot=... -o module.wasm module.c`
- **Rust**: `cargo build --target wasm32-unknown-unknown`
- **AssemblyScript**: `asc module.ts -o module.wasm`

## Platform Support

### Linux VM / Cloud Instances

```bash
./bootstrap.sh
```

### Android Termux

```bash
pkg update && pkg install git python cmake clang
chmod +x bootstrap.sh
./bootstrap.sh
```

### Cloud Deployment

The bootstrap script automatically detects cloud environments (AWS, DigitalOcean, etc.) and configures appropriately.

## Environment Variables

- `BXTHRE3_CONTROLLER`: Controller IP address (auto-discovered by default)
- `RAM_PER_NODE`: RAM per logical node in MB (default: 128)

## Networking

- Default Controller Port: 5000
- Auto-discovery via LAN broadcast
- Multi-device support: Multiple devices can connect to the same Controller

## Monitoring

The UI Node provides:

- Live node status (connected nodes, RAM usage, task counts)
- DAG execution status (pending, running, completed tasks)
- Task results and outputs
- Real-time progress updates

## Scaling Logic

The Node Manager calculates the number of logical nodes based on:

```
max_nodes = (available_ram - min_free_ram) / ram_per_node
```

Where:
- `available_ram`: Current available system RAM
- `min_free_ram`: Minimum RAM to keep free for the OS (default: 512MB)
- `ram_per_node`: User-defined RAM per node (default: 128MB)

Nodes are automatically:
- Spawned when RAM becomes available
- Stopped when RAM is needed
- Restarted on failure

## Logs

Logs are stored in the `logs/` directory:
- `ui_node.log` - UI Node logs
- `controller.log` - Controller logs
- `node_manager.log` - Node Manager logs
- `host_<node_id>.log` - Individual Host Node logs

## Troubleshooting

### Controller not found

Check that the Controller is running and accessible:
```bash
curl http://controller_ip:5000
```

### WASM execution errors

Ensure:
1. Wasm3 runtime is built: `ls wasm_modules/m3/wasm3`
2. WASM modules are valid: `file wasm_modules/*.wasm`
3. Module paths are correct in DAG definitions

### Out of memory errors

Reduce RAM per node:
```bash
python3 bxthre3_node_manager.py --ram-per-node 64
```

## Contributing

Contributions are welcome! Areas for improvement:
- Additional WASM module examples
- More sophisticated scheduling algorithms
- Enhanced monitoring and logging
- Support for additional cloud providers
- Security and authentication features

## License

MIT License - See LICENSE file for details

## Contact

For issues, questions, or contributions, please visit:
https://github.com/bxthre3/bxthre3