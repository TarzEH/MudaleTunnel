# Docker Setup for MudaleTunnel

This guide explains how to run MudaleTunnel using Docker and access SSH tunnels from your host machine.

## Important: Docker Networking for SSH Tunnels

**SSH tunnels created inside Docker containers bind to the container's network namespace, not the host.** This means:

- ✅ **Web interface** works fine (port 8000 is mapped)
- ⚠️ **SSH tunnels** are only accessible from inside the container by default

To make tunnels accessible from your host, you have two options:

### Option 1: Host Network Mode (Linux only, Recommended)

Use Docker's host network mode to share the host's network stack:

```bash
docker run -d \
  --name mudaletunnel \
  --network host \
  -v ~/.ssh:/root/.ssh:ro \
  mudaletunnel \
  python main.py web --host 0.0.0.0 --port 8000
```

**Pros:**
- Tunnels are directly accessible from host at `localhost:PORT`
- No port mapping needed
- Best performance

**Cons:**
- Only works on Linux (not Docker Desktop for Windows/Mac)
- Container uses host's network directly (less isolation)

### Option 2: Bridge Network with Port Mapping (All Platforms)

Map specific tunnel ports when you know them in advance:

```bash
docker run -d \
  --name mudaletunnel \
  -p 8000:8000 \
  -p 1080:1080 \
  -p 8080:8080 \
  -p 3306:3306 \
  -v ~/.ssh:/root/.ssh:ro \
  mudaletunnel \
  python main.py web --host 0.0.0.0 --port 8000
```

**Pros:**
- Works on all platforms (Windows, Mac, Linux)
- Better isolation

**Cons:**
- Must map ports in advance
- Need to restart container to add new ports

## Prerequisites

- Docker installed on your system
- Docker Compose (optional, for easier management)

## Quick Start

### Using Docker Compose (Recommended)

#### Standard Mode (Bridge Network)

1. **Start the web interface:**
   ```bash
   docker-compose up -d
   ```

2. **Access the web interface:**
   Open your browser at `http://localhost:8000`

3. **View logs:**
   ```bash
   docker-compose logs -f
   ```

4. **Stop the container:**
   ```bash
   docker-compose down
   ```

**Note:** In this mode, SSH tunnels are only accessible from inside the container.

#### Host Network Mode (Linux only, for host-accessible tunnels)

1. **Edit `docker-compose.yml`:**
   - Comment out the `ports:` section (add `#` before `ports:`)
   - Uncomment `network_mode: host` (remove `#` before it)

2. **Start the web interface:**
   ```bash
   docker-compose up -d
   ```

3. **Access the web interface:**
   Open your browser at `http://localhost:8000`

**Note:** In this mode, SSH tunnels are accessible from your host at `localhost:PORT`.

### Using Docker Directly

1. **Build the image:**
   ```bash
   docker build -t mudaletunnel .
   ```

2. **Run web interface (Bridge Network - tunnels only in container):**
   ```bash
   docker run -d \
     --name mudaletunnel \
     -p 8000:8000 \
     -v ~/.ssh:/root/.ssh:ro \
     mudaletunnel \
     python main.py web --host 0.0.0.0 --port 8000
   ```

3. **Run web interface (Host Network - tunnels accessible from host, Linux only):**
   ```bash
   docker run -d \
     --name mudaletunnel \
     --network host \
     -v ~/.ssh:/root/.ssh:ro \
     mudaletunnel \
     python main.py web --host 0.0.0.0 --port 8000
   ```

4. **Run CLI mode (interactive):**
   ```bash
   docker run -it --rm \
     --name mudaletunnel-cli \
     -v ~/.ssh:/root/.ssh:ro \
     mudaletunnel \
     python main.py cli
   ```

5. **Run CLI mode with host network (Linux only):**
   ```bash
   docker run -it --rm \
     --name mudaletunnel-cli \
     --network host \
     -v ~/.ssh:/root/.ssh:ro \
     mudaletunnel \
     python main.py cli
   ```

## Configuration

### Custom Port

To use a different port for the web interface:

```bash
docker run -d \
  --name mudaletunnel \
  -p 8080:8080 \
  mudaletunnel \
  python main.py web --host 0.0.0.0 --port 8080
```

Or in `docker-compose.yml`, change the port mapping:
```yaml
ports:
  - "8080:8080"
```

### SSH Key Access

The Docker container mounts your local `~/.ssh` directory (read-only) to use your SSH keys. Make sure your SSH keys are properly configured on your host machine.

### Environment Variables

You can set environment variables in `docker-compose.yml`:

```yaml
environment:
  - PYTHONUNBUFFERED=1
  - CUSTOM_VAR=value
```

## Accessing Tunnels from Host

### Scenario 1: Using Host Network Mode (Linux)

If you're using `--network host` or `network_mode: host`:

1. Create a tunnel through the web interface (e.g., port 8080)
2. Access it directly from your host: `http://localhost:8080`
3. No additional configuration needed

### Scenario 2: Using Bridge Network (Windows/Mac)

If you're using standard Docker networking:

**Option A: Map ports in advance**
```bash
docker run -d \
  --name mudaletunnel \
  -p 8000:8000 \
  -p 1080:1080 \      # For SOCKS proxy
  -p 8080:8080 \      # For HTTP tunnel
  -p 3306:3306 \      # For MySQL tunnel
  -v ~/.ssh:/root/.ssh:ro \
  mudaletunnel
```

Then create tunnels using these mapped ports.

**Option B: Use container IP**
1. Get container IP: `docker inspect mudaletunnel | grep IPAddress`
2. Access tunnels via container IP instead of localhost
3. Note: This is less convenient but works

**Option C: Use Docker exec to access from inside**
```bash
# Create tunnel via web UI
# Then access from inside container:
docker exec -it mudaletunnel curl http://localhost:8080
```

## Troubleshooting

### Container can't access SSH

If you need to use SSH keys, make sure they're in `~/.ssh` on your host and the volume is mounted correctly.

### Tunnels not accessible from host

- **Linux:** Use `--network host` mode
- **Windows/Mac:** Map ports in advance or use container IP
- **All platforms:** Check that ports aren't already in use on host

### Port already in use

If port 8000 is already in use, change the port mapping:
```bash
docker run -d -p 8080:8000 mudaletunnel
```

### View container logs

```bash
docker logs mudaletunnel
# or with docker-compose
docker-compose logs -f
```

### Execute commands in running container

```bash
docker exec -it mudaletunnel /bin/bash
```

## Building from Source

If you modify the code, rebuild the image:

```bash
docker build -t mudaletunnel .
```

Or with docker-compose:

```bash
docker-compose build
docker-compose up -d
```
