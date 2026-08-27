# ARCH 1.1 连续滑动热力图展示脚本说明

## 目标

用于真实 8x8 织物压阻矩阵的连续滑动动态响应观察。脚本不限时间运行，实时显示压力差值热力图，可同步保存连续 CSV 数据，适合做 ARCH 1.1 超分辨率滑动轨迹实验前的状态检查与素材采集。

## 脚本位置

```powershell
tools/live_rebuild_h4_unlimited.py
```

## 默认坐标映射

脚本默认采用 H4 阶段确认后的真实传感器物理显示映射：

- `ROW0` 显示在上方。
- `COL0` 显示在右侧。
- 右上角为 `COL0 ROW0`。
- 右下角为 `COL0 ROW7`。

因此显示热力图中的横向物理坐标会相对原始 COL 编号左右翻转，使屏幕位置尽量与实际按压位置一致。

## 推荐启动命令

使用已有 H4 空载基线，直接进入差值热力图：

```powershell
python tools/live_rebuild_h4_unlimited.py --port COM7 --baseline-json data/rebuild_h4/20260818_real_sensor_run01/baseline_stats.json --mode delta --vmax 1200
```

现场重新采集 120 帧空载基线后进入显示：

```powershell
python tools/live_rebuild_h4_unlimited.py --port COM7 --baseline-frames 120 --mode delta --vmax 1200
```

重新采集基线，并保存本次连续滑动数据：

```powershell
python tools/live_rebuild_h4_unlimited.py --port COM7 --baseline-frames 120 --save-baseline-json data/rebuild_h4/live_baseline_20260819.json --save-csv data/rebuild_h4/live_slide_20260819.csv --mode delta --vmax 1200
```

查看原始电压热力图：

```powershell
python tools/live_rebuild_h4_unlimited.py --port COM7 --baseline-json data/rebuild_h4/20260818_real_sensor_run01/baseline_stats.json --mode raw --raw-vmin 1000 --raw-vmax 2500
```

## 运行方式

1. 传感器空载，先运行脚本。
2. 若使用 `--baseline-frames`，等待基线采集完成。
3. 进入实时热力图后，进行连续滑动、单点按压或多点按压。
4. 使用 `Ctrl+C` 结束。

## 输出说明

若指定 `--save-csv`，脚本会持续写入每一帧的 8 行原始矩阵数据：

- `frame_seq`：固件输出帧号。
- `host_time_s`：电脑接收时间。
- `raw_row`：原始 ROW 编号。
- `display_y`：映射后的显示 Y 坐标。
- `c0_mv` 到 `c7_mv`：原始 COL 顺序下的电压值。
- `c0_delta_mv` 到 `c7_delta_mv`：相对基线差值。
- `peak_raw_row` / `peak_raw_col`：当前帧最大响应的原始位置。
- `peak_display_x` / `peak_display_y`：当前帧最大响应的物理显示位置。
- `peak_delta_mv`：当前帧最大差值。

## 备注

该脚本用于实时展示与长时间采集，不会自动生成科研图。连续滑动实验完成后，可基于保存的 CSV 进一步生成轨迹图、时序曲线、峰值路径图和超分辨率重建对比图。
