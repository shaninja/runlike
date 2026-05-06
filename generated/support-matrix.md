# Runlike support matrix

Generated from `generated/probe-results.json`, `spec/option-dictionary/`, and `tests/probes/`.

Target: `linux-docker-25.0.5-api-1.44`.

Summary: 39 supported, 0 partial, 38 unsupported, 16 out of scope, 10 needs special runner.

| Option | Flag | Container name | Stdin | Scope | Reason |
| --- | --- | --- | --- | --- | --- |
| add-host | `--add-host` | supported | supported | in_scope |  |
| annotation | `--annotation` | unsupported | unsupported | in_scope |  |
| attach | `--attach` | supported | supported | in_scope |  |
| blkio-weight | `--blkio-weight` | unsupported | unsupported | in_scope |  |
| blkio-weight-device | `--blkio-weight-device` | needs special runner | needs special runner | needs special runner | needs_special_host_device |
| cap-add | `--cap-add` | supported | supported | in_scope |  |
| cap-drop | `--cap-drop` | supported | supported | in_scope |  |
| cgroup-parent | `--cgroup-parent` | unsupported | unsupported | in_scope |  |
| cgroupns | `--cgroupns` | unsupported | unsupported | in_scope |  |
| cidfile | `--cidfile` | out_of_scope | out_of_scope | out_of_scope | client_side_only |
| cpu-count | `--cpu-count` | out_of_scope | out_of_scope | out_of_scope | windows_only |
| cpu-percent | `--cpu-percent` | out_of_scope | out_of_scope | out_of_scope | windows_only |
| cpu-period | `--cpu-period` | unsupported | unsupported | in_scope |  |
| cpu-quota | `--cpu-quota` | unsupported | unsupported | in_scope |  |
| cpu-rt-period | `--cpu-rt-period` | needs special runner | needs special runner | needs special runner | needs_rt_runtime_runner |
| cpu-rt-runtime | `--cpu-rt-runtime` | needs special runner | needs special runner | needs special runner | needs_rt_runtime_runner |
| cpu-shares | `--cpu-shares` | unsupported | unsupported | in_scope |  |
| cpus | `--cpus` | unsupported | unsupported | in_scope |  |
| cpuset-cpus | `--cpuset-cpus` | supported | supported | in_scope |  |
| cpuset-mems | `--cpuset-mems` | supported | supported | in_scope |  |
| detach | `--detach` | supported | supported | in_scope |  |
| detach-keys | `--detach-keys` | out_of_scope | out_of_scope | out_of_scope | client_side_only |
| device | `--device` | supported | supported | in_scope |  |
| device-cgroup-rule | `--device-cgroup-rule` | needs special runner | needs special runner | needs special runner | needs_special_host_device |
| device-read-bps | `--device-read-bps` | needs special runner | needs special runner | needs special runner | needs_special_host_device |
| device-read-iops | `--device-read-iops` | needs special runner | needs special runner | needs special runner | needs_special_host_device |
| device-write-bps | `--device-write-bps` | needs special runner | needs special runner | needs special runner | needs_special_host_device |
| device-write-iops | `--device-write-iops` | needs special runner | needs special runner | needs special runner | needs_special_host_device |
| disable-content-trust | `--disable-content-trust` | out_of_scope | out_of_scope | out_of_scope | client_side_only |
| dns | `--dns` | supported | supported | in_scope |  |
| dns-option | `--dns-option` | unsupported | unsupported | in_scope |  |
| dns-search | `--dns-search` | unsupported | unsupported | in_scope |  |
| domainname | `--domainname` | unsupported | unsupported | in_scope |  |
| entrypoint | `--entrypoint` | supported | supported | in_scope |  |
| env | `--env` | supported | supported | in_scope |  |
| env-file | `--env-file` | out_of_scope | out_of_scope | out_of_scope | non_observable_from_inspect |
| expose | `--expose` | supported | supported | in_scope |  |
| gpus | `--gpus` | needs special runner | needs special runner | needs special runner | needs_gpu_runner |
| group-add | `--group-add` | unsupported | unsupported | in_scope |  |
| health-cmd | `--health-cmd` | unsupported | unsupported | in_scope |  |
| health-interval | `--health-interval` | unsupported | unsupported | in_scope |  |
| health-retries | `--health-retries` | unsupported | unsupported | in_scope |  |
| health-start-interval | `--health-start-interval` | unsupported | unsupported | in_scope |  |
| health-start-period | `--health-start-period` | unsupported | unsupported | in_scope |  |
| health-timeout | `--health-timeout` | unsupported | unsupported | in_scope |  |
| help | `--help` | out_of_scope | out_of_scope | out_of_scope | client_side_only |
| hostname | `--hostname` | supported | supported | in_scope |  |
| init | `--init` | unsupported | unsupported | in_scope |  |
| interactive | `--interactive` | supported | supported | in_scope |  |
| io-maxbandwidth | `--io-maxbandwidth` | out_of_scope | out_of_scope | out_of_scope | windows_only |
| io-maxiops | `--io-maxiops` | out_of_scope | out_of_scope | out_of_scope | windows_only |
| ip | `--ip` | supported | supported | in_scope |  |
| ip6 | `--ip6` | supported | supported | in_scope |  |
| ipc | `--ipc` | unsupported | unsupported | in_scope |  |
| isolation | `--isolation` | out_of_scope | out_of_scope | out_of_scope | windows_only |
| kernel-memory | `--kernel-memory` | unsupported | unsupported | in_scope |  |
| label | `--label` | supported | supported | in_scope |  |
| label-file | `--label-file` | out_of_scope | out_of_scope | out_of_scope | non_observable_from_inspect |
| link | `--link` | supported | supported | in_scope |  |
| link-local-ip | `--link-local-ip` | unsupported | unsupported | in_scope |  |
| log-driver | `--log-driver` | supported | supported | in_scope |  |
| log-opt | `--log-opt` | supported | supported | in_scope |  |
| mac-address | `--mac-address` | supported | supported | in_scope |  |
| memory | `--memory` | supported | supported | in_scope |  |
| memory-reservation | `--memory-reservation` | supported | supported | in_scope |  |
| memory-swap | `--memory-swap` | unsupported | unsupported | in_scope |  |
| memory-swappiness | `--memory-swappiness` | unsupported | unsupported | in_scope |  |
| mount | `--mount` | supported | supported | in_scope |  |
| name | `--name` | supported | supported | in_scope |  |
| network | `--network` | supported | supported | in_scope |  |
| network-alias | `--network-alias` | out_of_scope | out_of_scope | out_of_scope | docker_inspect_aliases_include_implicit_container_aliases |
| no-healthcheck | `--no-healthcheck` | unsupported | unsupported | in_scope |  |
| oom-kill-disable | `--oom-kill-disable` | unsupported | unsupported | in_scope |  |
| oom-score-adj | `--oom-score-adj` | unsupported | unsupported | in_scope |  |
| pid | `--pid` | supported | supported | in_scope |  |
| pids-limit | `--pids-limit` | unsupported | unsupported | in_scope |  |
| platform | `--platform` | out_of_scope | out_of_scope | out_of_scope | non_observable_from_inspect |
| privileged | `--privileged` | supported | supported | in_scope |  |
| publish | `--publish` | supported | supported | in_scope |  |
| publish-all | `--publish-all` | supported | supported | in_scope |  |
| pull | `--pull` | out_of_scope | out_of_scope | out_of_scope | client_side_only |
| quiet | `--quiet` | out_of_scope | out_of_scope | out_of_scope | client_side_only |
| read-only | `--read-only` | unsupported | unsupported | in_scope |  |
| restart | `--restart` | supported | supported | in_scope |  |
| rm | `--rm` | supported | supported | in_scope |  |
| runtime | `--runtime` | supported | supported | in_scope |  |
| security-opt | `--security-opt` | unsupported | unsupported | in_scope |  |
| shm-size | `--shm-size` | supported | supported | in_scope |  |
| sig-proxy | `--sig-proxy` | out_of_scope | out_of_scope | out_of_scope | client_side_only |
| stop-signal | `--stop-signal` | unsupported | unsupported | in_scope |  |
| stop-timeout | `--stop-timeout` | unsupported | unsupported | in_scope |  |
| storage-opt | `--storage-opt` | needs special runner | needs special runner | needs special runner | needs_storage_driver_runner |
| sysctl | `--sysctl` | unsupported | unsupported | in_scope |  |
| tmpfs | `--tmpfs` | unsupported | unsupported | in_scope |  |
| tty | `--tty` | supported | supported | in_scope |  |
| ulimit | `--ulimit` | unsupported | unsupported | in_scope |  |
| user | `--user` | supported | supported | in_scope |  |
| userns | `--userns` | unsupported | unsupported | in_scope |  |
| uts | `--uts` | unsupported | unsupported | in_scope |  |
| volume | `--volume` | supported | supported | in_scope |  |
| volume-driver | `--volume-driver` | unsupported | unsupported | in_scope |  |
| volumes-from | `--volumes-from` | supported | supported | in_scope |  |
| workdir | `--workdir` | supported | supported | in_scope |  |
