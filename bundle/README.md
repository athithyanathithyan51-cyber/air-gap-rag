# bundle/

Builds the single offline transfer bundle (Phase 2): saved Docker images, the built frontend, model files, a SHA-256 manifest of every artifact and the install/uninstall/rollback scripts.

The bundle is built on a connected Linux or WSL machine and moved to the air-gapped host by USB. It is too large (est. 7–9 GB, **untested**) for CI artifact storage.
