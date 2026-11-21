<img width="1901" height="977" alt="record" src="https://github.com/user-attachments/assets/76f371d8-e112-4b32-bdbd-949278b8fd7a" />

<img width="1097" height="781" alt="image" src="https://github.com/user-attachments/assets/f549ca5f-600f-4aee-914e-6ac4b7fffe00" />

# CAN Monitor

A small desktop tool (PyQt6 + pyqtgraph) to view, plot, filter and log CAN traffic.
It runs **without hardware**: a built-in simulator produces realistic traffic.

## Features
- Live plots of selected signals (10 s window)
- Monitor view: latest frame per ID with count, period and decoded signals
- Rolling trace of the last 1000 frames
- ID filter (hex, comma separated)
- Record to CSV and read logs back
- Core logic (frames, signal encode/decode, simulator, logger, filters) is GUI-free and unit tested

## Run
```
pip install -r requirements.txt
python main.py
python tests/test_core.py -v
```

## Structure
- `core/` - GUI-free logic
- `tests/` - unit tests
- `main.py` - PyQt6 application
