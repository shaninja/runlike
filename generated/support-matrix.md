# Runlike support matrix

Generated from `generated/probe-results.json`, `spec/option-dictionary/`, and `tests/probes/`.

Target: `linux-docker-25.0.5-api-1.44`.

Summary: 75 supported, 1 partial, 0 unsupported, 16 out of scope, 11 needs special runner.

| Option | Flag | Container name | Stdin | Scope | Reason | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| add-host | `--add-host` | supported | supported | in_scope |  |  |
| annotation | `--annotation` | supported | supported | in_scope |  |  |
| attach | `--attach` | supported | supported | in_scope |  |  |
| blkio-weight | `--blkio-weight` | supported | supported | in_scope |  |  |
| blkio-weight-device | `--blkio-weight-device` | needs special runner | needs special runner | needs special runner | needs_special_host_device | Blocked on the standard pinned Docker 25 runner. Docker accepts the flag but warns that per-device block I/O weight is unsupported and discards the setting, so HostConfig.BlkioWeightDevice is empty.<br>Future verification requires a runner with per-device block I/O weight support and a stable host block device path. |
| cap-add | `--cap-add` | supported | supported | in_scope |  |  |
| cap-drop | `--cap-drop` | supported | supported | in_scope |  |  |
| cgroup-parent | `--cgroup-parent` | supported | supported | in_scope |  |  |
| cgroupns | `--cgroupns` | supported | supported | in_scope |  |  |
| cidfile | `--cidfile` | out_of_scope | out_of_scope | out_of_scope | client_side_only |  |
| cpu-count | `--cpu-count` | out_of_scope | out_of_scope | out_of_scope | windows_only |  |
| cpu-percent | `--cpu-percent` | out_of_scope | out_of_scope | out_of_scope | windows_only |  |
| cpu-period | `--cpu-period` | supported | supported | in_scope |  |  |
| cpu-quota | `--cpu-quota` | supported | supported | in_scope |  |  |
| cpu-rt-period | `--cpu-rt-period` | needs special runner | needs special runner | needs special runner | needs_rt_runtime_runner | Blocked on the standard pinned Docker 25 runner. Docker refuses container creation with this flag because the kernel does not support Docker CPU real-time scheduling in this environment.<br>Future verification requires a runner with Linux real-time scheduler support enabled and Docker configured for CPU real-time runtime. |
| cpu-rt-runtime | `--cpu-rt-runtime` | needs special runner | needs special runner | needs special runner | needs_rt_runtime_runner | Blocked on the standard pinned Docker 25 runner. Docker refuses container creation with this flag because the kernel does not support Docker CPU real-time scheduling in this environment.<br>Future verification requires a runner with Linux real-time scheduler support enabled and Docker configured for CPU real-time runtime. |
| cpu-shares | `--cpu-shares` | supported | supported | in_scope |  |  |
| cpus | `--cpus` | supported | supported | in_scope |  |  |
| cpuset-cpus | `--cpuset-cpus` | supported | supported | in_scope |  |  |
| cpuset-mems | `--cpuset-mems` | supported | supported | in_scope |  |  |
| detach | `--detach` | supported | supported | in_scope |  |  |
| detach-keys | `--detach-keys` | out_of_scope | out_of_scope | out_of_scope | client_side_only |  |
| device | `--device` | supported | supported | in_scope |  |  |
| device-cgroup-rule | `--device-cgroup-rule` | supported | supported | in_scope |  | Supported on the standard pinned Docker 25 runner. The create/inspect probe stores HostConfig.DeviceCgroupRules and round-trips the same rule. |
| device-read-bps | `--device-read-bps` | needs special runner | needs special runner | needs special runner | needs_special_host_device | Blocked on the standard pinned Docker 25 runner. Docker accepts the flag but the runner reports no io.max read-bps support, so HostConfig.BlkioDeviceReadBps is empty.<br>Future verification requires a runner with block I/O throttle support and a stable host block device path. |
| device-read-iops | `--device-read-iops` | needs special runner | needs special runner | needs special runner | needs_special_host_device | Blocked on the standard pinned Docker 25 runner. Docker accepts the flag but the runner reports no io.max read-iops support, so HostConfig.BlkioDeviceReadIOps is empty.<br>Future verification requires a runner with block I/O throttle support and a stable host block device path. |
| device-write-bps | `--device-write-bps` | needs special runner | needs special runner | needs special runner | needs_special_host_device | Blocked on the standard pinned Docker 25 runner. Docker accepts the flag but the runner reports no io.max write-bps support, so HostConfig.BlkioDeviceWriteBps is empty.<br>Future verification requires a runner with block I/O throttle support and a stable host block device path. |
| device-write-iops | `--device-write-iops` | needs special runner | needs special runner | needs special runner | needs_special_host_device | Blocked on the standard pinned Docker 25 runner. Docker accepts the flag but the runner reports no io.max write-iops support, so HostConfig.BlkioDeviceWriteIOps is empty.<br>Future verification requires a runner with block I/O throttle support and a stable host block device path. |
| disable-content-trust | `--disable-content-trust` | out_of_scope | out_of_scope | out_of_scope | client_side_only |  |
| dns | `--dns` | supported | supported | in_scope |  |  |
| dns-option | `--dns-option` | supported | supported | in_scope |  |  |
| dns-search | `--dns-search` | supported | supported | in_scope |  |  |
| domainname | `--domainname` | supported | supported | in_scope |  |  |
| entrypoint | `--entrypoint` | supported | supported | in_scope |  |  |
| env | `--env` | supported | supported | in_scope |  |  |
| env-file | `--env-file` | out_of_scope | out_of_scope | out_of_scope | non_observable_from_inspect |  |
| expose | `--expose` | supported | supported | in_scope |  |  |
| gpus | `--gpus` | partial | partial | in_scope | needs_gpu_runner_for_runtime_execution | Create/inspect round-trip support is covered for --gpus=all on the standard pinned Docker 25 runner.<br>Starting a GPU container is not covered on the pinned runner because it has no GPU runtime or GPU hardware.<br>Runtime execution requires a GPU runner with GPU hardware and the Docker GPU runtime, such as NVIDIA Container Toolkit. |
| group-add | `--group-add` | supported | supported | in_scope |  |  |
| health-cmd | `--health-cmd` | supported | supported | in_scope |  |  |
| health-interval | `--health-interval` | supported | supported | in_scope |  |  |
| health-retries | `--health-retries` | supported | supported | in_scope |  |  |
| health-start-interval | `--health-start-interval` | supported | supported | in_scope |  |  |
| health-start-period | `--health-start-period` | supported | supported | in_scope |  |  |
| health-timeout | `--health-timeout` | supported | supported | in_scope |  |  |
| help | `--help` | out_of_scope | out_of_scope | out_of_scope | client_side_only |  |
| hostname | `--hostname` | supported | supported | in_scope |  |  |
| init | `--init` | supported | supported | in_scope |  |  |
| interactive | `--interactive` | supported | supported | in_scope |  |  |
| io-maxbandwidth | `--io-maxbandwidth` | out_of_scope | out_of_scope | out_of_scope | windows_only |  |
| io-maxiops | `--io-maxiops` | out_of_scope | out_of_scope | out_of_scope | windows_only |  |
| ip | `--ip` | supported | supported | in_scope |  |  |
| ip6 | `--ip6` | supported | supported | in_scope |  |  |
| ipc | `--ipc` | supported | supported | in_scope |  |  |
| isolation | `--isolation` | out_of_scope | out_of_scope | out_of_scope | windows_only |  |
| kernel-memory | `--kernel-memory` | needs special runner | needs special runner | needs special runner | needs_cgroup_v1_kernel_memory_accounting |  |
| label | `--label` | supported | supported | in_scope |  |  |
| label-file | `--label-file` | out_of_scope | out_of_scope | out_of_scope | non_observable_from_inspect |  |
| link | `--link` | supported | supported | in_scope |  |  |
| link-local-ip | `--link-local-ip` | supported | supported | in_scope |  |  |
| log-driver | `--log-driver` | supported | supported | in_scope |  |  |
| log-opt | `--log-opt` | supported | supported | in_scope |  |  |
| mac-address | `--mac-address` | supported | supported | in_scope |  |  |
| memory | `--memory` | supported | supported | in_scope |  |  |
| memory-reservation | `--memory-reservation` | supported | supported | in_scope |  |  |
| memory-swap | `--memory-swap` | supported | supported | in_scope |  |  |
| memory-swappiness | `--memory-swappiness` | needs special runner | needs special runner | needs special runner | needs_cgroup_v1_memory_swappiness |  |
| mount | `--mount` | supported | supported | in_scope |  |  |
| name | `--name` | supported | supported | in_scope |  |  |
| network | `--network` | supported | supported | in_scope |  |  |
| network-alias | `--network-alias` | out_of_scope | out_of_scope | out_of_scope | docker_inspect_aliases_include_implicit_container_aliases |  |
| no-healthcheck | `--no-healthcheck` | supported | supported | in_scope |  |  |
| oom-kill-disable | `--oom-kill-disable` | needs special runner | needs special runner | needs special runner | needs_kernel_oom_kill_disable_support |  |
| oom-score-adj | `--oom-score-adj` | supported | supported | in_scope |  |  |
| pid | `--pid` | supported | supported | in_scope |  |  |
| pids-limit | `--pids-limit` | supported | supported | in_scope |  |  |
| platform | `--platform` | out_of_scope | out_of_scope | out_of_scope | non_observable_from_inspect |  |
| privileged | `--privileged` | supported | supported | in_scope |  |  |
| publish | `--publish` | supported | supported | in_scope |  |  |
| publish-all | `--publish-all` | supported | supported | in_scope |  |  |
| pull | `--pull` | out_of_scope | out_of_scope | out_of_scope | client_side_only |  |
| quiet | `--quiet` | out_of_scope | out_of_scope | out_of_scope | client_side_only |  |
| read-only | `--read-only` | supported | supported | in_scope |  |  |
| restart | `--restart` | supported | supported | in_scope |  |  |
| rm | `--rm` | supported | supported | in_scope |  |  |
| runtime | `--runtime` | supported | supported | in_scope |  |  |
| security-opt | `--security-opt` | supported | supported | in_scope |  |  |
| shm-size | `--shm-size` | supported | supported | in_scope |  |  |
| sig-proxy | `--sig-proxy` | out_of_scope | out_of_scope | out_of_scope | client_side_only |  |
| stop-signal | `--stop-signal` | supported | supported | in_scope |  |  |
| stop-timeout | `--stop-timeout` | supported | supported | in_scope |  |  |
| storage-opt | `--storage-opt` | needs special runner | needs special runner | needs special runner | needs_storage_driver_runner | Blocked on the standard pinned Docker 25 runner. Docker refuses container creation because --storage-opt size requires overlay over XFS with project quotas.<br>Future verification requires a storage-specific runner using a Docker storage configuration that supports per-container storage options. |
| sysctl | `--sysctl` | supported | supported | in_scope |  |  |
| tmpfs | `--tmpfs` | supported | supported | in_scope |  |  |
| tty | `--tty` | supported | supported | in_scope |  |  |
| ulimit | `--ulimit` | supported | supported | in_scope |  |  |
| user | `--user` | supported | supported | in_scope |  |  |
| userns | `--userns` | supported | supported | in_scope |  |  |
| uts | `--uts` | supported | supported | in_scope |  |  |
| volume | `--volume` | supported | supported | in_scope |  |  |
| volume-driver | `--volume-driver` | supported | supported | in_scope |  |  |
| volumes-from | `--volumes-from` | supported | supported | in_scope |  |  |
| workdir | `--workdir` | supported | supported | in_scope |  |  |
