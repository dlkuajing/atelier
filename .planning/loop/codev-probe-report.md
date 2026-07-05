# ENGINE-03a CODE V Probe Report

Probe time: 2026-07-05
Host path checked: `D:\CODEV115`

## Summary

- Result: CODE V installation detected.
- Home: `D:\CODEV115`
- Version evidence:
  - `D:\CODEV115\codev.exe` file version: `11.5.27302701`
  - `D:\CODEV115\cvcommand.exe` file version: `11.5.27302701`
- Registry evidence:
  - `HKLM\SOFTWARE\WOW6432Node\Optical Research Associates\CODE V\11.5\Directories`
  - `CV_EXEC=D:\CODEV115`
  - `CV_DOC=D:\CODEV115\doc`
  - `CV_MACRO=D:\CODEV115\macro`
- Probe did not launch CODE V and did not modify license, sentinel, `.env`, or credentials.

## Executables

Root-level executable inventory under `D:\CODEV115`:

| File | Size bytes | File version |
| --- | ---: | --- |
| `AsphereWriter.exe` | 562536 | `11.5.27302.701` |
| `ChartGen.exe` | 241512 | `11.5.27302701` |
| `codev.exe` | 383848 | `11.5.27302701` |
| `codevm.exe` | 81181032 | `11.5.27302701` |
| `codevtodxf.exe` | 496488 | `11.5.27302701` |
| `cvcommand.exe` | 377704 | `11.5.27302701` |
| `cvcommandtest.exe` | 76648 | `11.5.27302701` |
| `cvconfig.exe` | 407912 | `11.5.27302701` |
| `cvconvertimage.exe` | 62824 | `11.5.27302701` |
| `cvedit.exe` | 188776 | `11.5.27302701` |
| `cvgui.exe` | 578920 | `11.5.27302701` |
| `cvplotview.exe` | 2660200 | `11.5.27302701` |
| `cvprintfile.exe` | 87912 | `11.5.27302701` |
| `cvpurge.exe` | 187240 | `11.5.27302701` |
| `hpgl.exe` | 533864 | `11.5.27302701` |
| `incversion.exe` | 196968 | `11.5.27302701` |
| `ORARegistryConverter.exe` | 100712 | `11.5.27302701` |
| `psplot.exe` | 91496 | `11.5.27302701` |
| `psprint.exe` | 486248 | `11.5.27302701` |
| `testumr.exe` | 66920 | `11.5.27302701` |
| `xcacls.exe` | 45056 | `5.2.3631.0 built by: lab03_dev(a-sgarde)` |
| `zeta.exe` | 545640 | `11.5.27302701` |
| `zygo2cve.exe` | 19816 | `11.5.27302701` |

## Macro Samples

`D:\CODEV115\macro` exists. First sampled `.seq` files:

- `abbe.seq`
- `aberrationgenerator.seq`
- `achromat.seq`
- `aligncds.seq`
- `apset.seq`
- `archerprv.seq`
- `AsphereExpert.seq`
- `AsphereExpert_analyze.seq`
- `AsphereExpert_main.seq`
- `AsphereExpert_print.seq`

## Manuals

`D:\CODEV115\doc` exists. Relevant manuals confirmed:

- `D:\CODEV115\doc\APIReferenceGuide.pdf`
- `D:\CODEV115\doc\CVSetup&OperationRM.pdf`
- `D:\CODEV115\doc\IntroductoryUG.pdf`
- `D:\CODEV115\doc\LensSystemSetupRM.pdf`
- `D:\CODEV115\doc\Macro-PLUS.pdf`
- `D:\CODEV115\doc\Optimization.pdf`
- `D:\CODEV115\doc\ReleaseNotes.pdf`

## Registry Integration

`app.core.engines.probe_code_v_installation()` now probes in this order:

1. Explicit environment home: `CODEV_HOME`, `CODE_V_HOME`, `CV_EXEC`.
2. Legacy explicit executable env vars, mapped back to their parent home.
3. Windows registry CODE V install roots.
4. Common root scan, including `D:\CODEV115`.
5. Unavailable fallback to `NullDeepEngine(reason="code_v_executable_not_found")`.

The registry still returns a registered `codev` engine only when an adapter is registered. Until
ENGINE-03b lands the batch adapter, a detected install with no registered adapter degrades to
`NullDeepEngine(reason="code_v_engine_not_registered")` with installation details attached.
