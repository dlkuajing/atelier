# Summary: Stage B reviewed-source pins on Windows

The reviewed predecessor pins were correct for Git/Ubuntu LF bytes, but the verifier hashed raw
Windows checkout bytes after `core.autocrlf` converted every line to CRLF. The descriptor now
canonicalizes only a uniform CRLF checkout to the reviewed LF representation. Mixed line endings,
bare CR, pin drift, and all other content drift remain fail-closed.

The pin values were not updated. Targeted and full offline regression suites pass. This change only
restores cross-platform verification of an existing reviewed source; it does not create new Stage B
evidence, authorize a runner, or change any north-star gate.

Release truth: reviewed commit `2d36cb9096afb2c46100e40e484b5c4ad8930b9e` / tree
`839635e5ee732fa6a22ccba193deb27a90246efc`; PR #84 CI run `29356580472` success; merge
`42803f8de6c6d8f6a2dbd5a0d4eb0c2ed8cf5ad7` retained the same tree; matching main CI run
`29359056663` success.
