# Security policy

Security updates are provided for the latest published KurrentScholar release. Report suspected
vulnerabilities privately to [jonas.hummel@kit.edu](mailto:jonas.hummel@kit.edu) before opening a public
issue. Include the KurrentScholar version and a minimal reproduction, but do not attach private
manuscripts, credentials, or identifying local paths.

KurrentScholar performs manuscript processing locally, loads pinned safetensors with remote code
disabled, and treats document parsers as a security boundary. Download installers only from the
repository's GitHub Releases page and verify the accompanying SHA-256 checksum. The current Windows
installer is not code-signed, so Windows may display an unknown-publisher warning.

