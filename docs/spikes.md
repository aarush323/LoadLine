
---
# Spike run 2026-10-10T09:03:01Z

## S-DOCKER
- egress from internal network: UNEXPECTED success (fail)
- alias reachability: pass
- probe candidate image: curlimages/curl:8.10.1
- probe digest: curlimages/curl@sha256:d9b4541e214bcd85196d6e92e2753ac6d0ea699f0af5741f8c6cccbfcf00ef4b

## S-GEN
- k6 image: grafana/k6:0.54.0
- k6 digest: grafana/k6@sha256:1f40432b1cbe7234e977f96c362c9bc550a2d2b583d014dd8669fe40d3e9e755
- k6 stdin smoke:      vus_max........................: 1       min=1      max=1


running (00m02.8s), 0/1 VUs, 3 complete and 0 interrupted iterations
default ✓ [ 100% ] 1 VUs  00m02.8s/10m0s  3/3 shared iters

## S-CGROUP
- docker stats json sample: {"BlockIO":"0B / 0B","CPUPerc":"0.00%","Container":"c20728a94f11b340afaa594ce8d7e9f2321cbd00ded40c6420cb85b6d54a3035","ID":"c20728a94f11","MemPerc":"0.00%","MemUsage":"672KiB / 15.45GiB","Name":"ferve...

## S-ENTIRE
- entire: Entire CLI 0.11.4
- graph: v0.4.0
- capabilities: {"schema_version":"1.1","provider":"entire-graph","supported_file_extensions":[".4th",".abap",".agda",".ahk",".applescript",".as",".asm",".astro",".aug",".awk",".bal",".bas",".bash",".bf",".bib",".bicep",".blade.php",".bnf",".boo",".bzl",".c",".cabal",".cc",".ceylon",".cfm",".clj",".cljc",".cljs",".
