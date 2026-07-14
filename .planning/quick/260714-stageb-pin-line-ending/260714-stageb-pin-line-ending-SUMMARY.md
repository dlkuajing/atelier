# Summary: Stage B reviewed-source pins on Windows

The reviewed predecessor pins were correct for Git/Ubuntu LF bytes, but the verifier hashed raw
Windows checkout bytes after `core.autocrlf` converted every line to CRLF. The descriptor now
canonicalizes only a uniform CRLF checkout to the reviewed LF representation. Mixed line endings,
bare CR, pin drift, and all other content drift remain fail-closed.

The pin values were not updated. Targeted and full offline regression suites pass. This change only
restores cross-platform verification of an existing reviewed source; it does not create new Stage B
evidence, authorize a runner, or change any north-star gate.
