# External simulation engine

`SeQUeNCe/` is a Git submodule of https://github.com/sequence-toolbox/SeQUeNCe,
pinned to version 0.8.1, commit `cf5283cdfd6692a82a090d15fb09fbc01bd322fc`.
Its upstream license is retained inside the submodule.

Initialize after cloning ACE:

```text
git submodule update --init --recursive
```

The source package is `SeQUeNCe/sequence/`: `kernel/` runs the discrete-event
simulation, `components/` models physical devices, and `network_management/`,
`resource_management/` and `entanglement_management/` implement base protocols.
ACE extensions remain under the repository's `ace/` folder.

`tools/run_ace.sh` uses this engine by default. For direct Python invocation,
put the absolute `third_party/SeQUeNCe` directory on PYTHONPATH. The historical
`.tmp/sequence-081` extraction is no longer required by this checkout.
Do not update the submodule revision without validating ACE compatibility.

Validated on 2026-10-30: all 82 engine Python files matched the prior runtime;
190 ACE tests passed. A complete QFT96 seed-6 C=4/ODG comparison reproduced
the previous mean latencies exactly (0.6587009809244068 ms compiler,
1.3344489197007225 ms ODG), with both runtime audits clean.
