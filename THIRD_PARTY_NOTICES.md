# Third party components

LIBERO-Remain, the evaluation contribution of Learning_Not_to_Act, uses the official [LIBERO](https://github.com/Lifelong-Robot-Learning/LIBERO) simulation package at commit `8f1084e3132a39270c3a13ebe37270a43ece2a01`. The setup script downloads and verifies upstream files; a generated evidence archive may include them together with LIBERO's original `LICENSE`. The Git checkout does not vendor the simulator assets.

The model adapters call separately installed official projects: [OpenVLA](https://github.com/openvla/openvla), [OpenVLA-OFT](https://github.com/moojink/openvla-oft), [OpenPI](https://github.com/Physical-Intelligence/openpi), [Isaac-GR00T](https://github.com/NVIDIA/Isaac-GR00T), and [UniVLA](https://github.com/OpenDriveLab/UniVLA). Their pinned revisions and checkpoint sources are documented in [the evaluation guide](docs/remaining_goals_six_model_evaluation.md) and the runtime configurations.

Model repositories, simulator dependencies and checkpoints retain their respective licenses and access conditions. No model weights are distributed in this repository. This notice does not assign a new license to third party content or constitute a project-wide license grant.
