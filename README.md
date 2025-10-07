# Homelab Health Checker

A modular health monitoring system for homelab servers that integrates with MOTD (Message of the Day) to show actionable alerts on SSH login.

## Features

- **Systemd Service Monitoring** - Detects failed or degraded services
- **Docker Container Health** - Identifies stopped, unhealthy, or dead containers
- **Smart Filtering** - Only shows problems that need attention
- **Color-Coded Alerts** - Visual hierarchy with severity levels
  - 🔴 Red: Critical issues (failed services, dead containers)
  - 🟡 Amber: Warnings (stopped containers, degraded services)
  - 🟣 Purple: Info messages
- **Extensible Architecture** - Easy to add new health checkers

## Installation

1. Clone the repository to your homelab server:
   ```bash
   cd ~/code
   git clone https://github.com/thatgardnerone/homelab-health.git
   cd homelab-health
   ```

2. Run the install script:
   ```bash
   ./install.sh
   ```

   This will:
   - Create a Python virtual environment
   - Install dependencies (pyyaml, docker)
   - Configure the script with the correct paths
   - Make the health checker executable

3. Test it:
   ```bash
   ./health_check.py
   ```

## MOTD Integration

To show health checks on SSH login, create `/etc/update-motd.d/89-health-check`:

```bash
#!/bin/sh
HEALTH_SCRIPT="/home/$(whoami)/code/homelab-health/health_check.py"

if [ -x "$HEALTH_SCRIPT" ]; then
    "$HEALTH_SCRIPT" 2>/dev/null || true
fi
```

Then make it executable:
```bash
sudo chmod +x /etc/update-motd.d/89-health-check
```

## Configuration

Edit `config.yaml` to customize monitoring:

```yaml
systemd:
  show_all_failed: true  # Show all failed services
  # monitor_specific:    # Or specify services to monitor
  #   - docker
  #   - nginx

docker:
  enabled: true
  show_stopped: true
  show_unhealthy: true
  ignore:  # Containers to ignore
    # - intentionally-stopped-container

display:
  show_ok_status: false  # Only show problems
  max_items: 10          # Limit output
```

## Extending

Add new health checkers by creating a class that inherits from `HealthChecker`:

```python
class CustomChecker(HealthChecker):
    def check(self) -> List[HealthIssue]:
        issues = []
        # Your health check logic here
        return issues
```

Then register it in `main()`:

```python
checkers = [
    SystemdChecker(config),
    DockerChecker(config),
    CustomChecker(config),  # Add your checker
]
```

## Performance

- Average execution time: ~120ms
- Suitable for MOTD without slowing down SSH login
- Uses isolated venv to avoid system Python conflicts

## Dependencies

- Python 3.8+
- pyyaml (for config parsing)
- docker (Python library, optional - falls back to CLI)

## License

Free to use and modify for your homelab!
