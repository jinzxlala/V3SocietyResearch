# 发给 AI 助手的操作指令

请先完整阅读本文件夹中的 `README_学生先读.md`、`数据字典.md` 和 `VERSION.txt`，再协助我操作。

我的当前任务只是在本地把 `input_saves` 中的 Victoria 3 `.v3` 存档导出为原始 CSV，还没有进入数据分析。请遵守以下边界：

1. 不得修改、移动、重命名或删除任何 `.v3` 文件；
2. 不得编辑 `tool/src`、`tool/bin` 或 `tool/student_export.py`；
3. 先确认操作系统、Python版本和存档位置；
4. Windows使用 `setup_windows.bat` 与 `export_windows.bat`；macOS使用 `bash setup_macos.sh` 与 `bash export_macos.sh`；
5. 缺少Python时，只指导我从Python官方渠道安装64位Python 3.11或更新版本；
6. 工具必须读取本机 Victoria 3 的 `game/common`；如果自动寻找失败，帮助我找到包含 `game/common` 的 Victoria 3 安装根目录，并把它填入 `game_path.txt`，不要伪造路径；
7. macOS若提示存档为 compressed/binary，不要尝试转换、改扩展名或重新保存；保留原件并交给Windows端处理；
8. 运行结束后，读取最新输出中的 `manifest.json`、`game_environment.json` 和 `export_log.txt`，报告成功数、失败数、游戏定义指纹、Steam build、每份存档的游戏版本、版本是否匹配、日期、SHA-256和ZIP位置；
9. 确认输出文件夹名为 `V3_raw_export_*`，且 `manifest.json` 中 `data_contract` 为 `raw_only`；
10. 确认 `game_definition_files_raw.csv` 和 `game_definition_keys_raw.csv` 已生成且没有解析失败；
11. 确认 `building_records_raw.csv` 包含全部建筑实体，而不是只含工业篮子；
12. 确认 `construction_queue_raw.csv` 将政府和私人队列用 `queue_kind` 区分；
13. 不要在这一步替我计算或新增 `basket_*`、`radicals_share`、阶层均值/差距、增长率、净余额或任何研究结论列；
14. 不要用猜测值补空白，不要把缺失值改成0；若失败，完整保留错误和输出文件夹。

开始前请先用一句话说明你看到的是Windows还是macOS，以及准备执行的第一步。每执行一步后先核对结果，再进入下一步。
