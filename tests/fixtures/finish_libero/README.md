# Pinned LIBERO robot source for CPU contract tests

`on_the_ground_panda.py.txt` is an unmodified copy of
[`libero/libero/envs/robots/on_the_ground_panda.py`](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/robots/on_the_ground_panda.py)
at LIBERO commit `8f1084e3132a39270c3a13ebe37270a43ece2a01`.
Its SHA-256 (UTF-8, LF) is
`7d580aeee632e164f327cf6b1951861bec40cf814cdbe92bcfc469a93e1f9fa8`.
The upstream MIT license is included in `LICENSE`.

`tests/test_finish_environment.py` verifies this hash, parses the source, and
executes only the `OnTheGroundPanda` class declaration in its official module
namespace. `ManipulatorModel` and XML-path resolution are non-physics stubs;
upstream imports are never executed. This preserves the actual direct base,
constructor XML path, default gripper and controller declarations. In
particular, the class does not inherit from `Panda`.

The fixture exercises robot identification and the existing fake gripper/OSC
contract. It does not instantiate LIBERO or MuJoCo, load XML, restore a state,
or establish real hold/release correctness. Physical preflight remains a
separate user-run validation step.
