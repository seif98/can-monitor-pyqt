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

<img width="1920" height="1080" alt="Main_window" src="https://github.com/user-attachments/assets/e23c7911-ea29-468b-bf20-bc4203c1f5d6" />

<img width="1901" height="977" alt="record" src="https://github.com/user-attachments/assets/76f371d8-e112-4b32-bdbd-949278b8fd7a" />
