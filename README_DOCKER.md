# Docker Setup for MudaleTunnel

This guide explains how to run MudaleTunnel using Docker.

## Prerequisites

- Docker installed on your system
- Docker Compose (optional, for easier management)

## Quick Start

### Using Docker Compose (Recommended)

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

### Using Docker Directly

1. **Build the image:**
   ```bash
   docker build -t mudaletunnel .
   ```

2. **Run web interface:**
   ```bash
   docker run -d \
     --name mudaletunnel \
     -p 8000:8000 \
     -v ~/.ssh:/root/.ssh:ro \
     mudaletunnel \
     python main.py web --host 0.0.0.0 --port 8000
   ```

3. **Run CLI mode (interactive):**
   ```bash
   docker run -it --rm \
     --name mudaletunnel-cli \
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

## Troubleshooting

### Container can't access SSH

If you need to use SSH keys, make sure they're in `~/.ssh` on your host and the volume is mounted correctly.

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
