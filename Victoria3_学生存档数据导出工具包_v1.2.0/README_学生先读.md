# Victoria 3 学生存档原始数据导出工具包

版本：1.2.0  
研究国家：比利时（BEL）  
用途：把 `.v3` 存档中的原始记录只读整理为 CSV，供后续数据清洗、合并与变量计算使用。

## 这一步只做“导出”，不做“分析”

工具会保留存档中的建筑、人口、州、机构、法律、趋势、预算槽位和当前建造队列等原始记录。它不会提前替学生计算：

- 工业篮子建筑等级、就业人数或占比；
- 各类建筑或各州的汇总量；
- 全国总人口、总劳动力；
- 激进派或效忠派比例；
- 各阶层生活水平均值、差距；
- 增长率、前后变化量、财政净余额。

这些变量由学生在数据处理阶段根据研究方案计算。若以后修改工业篮子或公式，只需重新处理 CSV，不必重新运行游戏。

## 为什么还要读取本机游戏目录

工具会在导出存档前找到本机 Victoria 3 安装目录，并读取与本研究有关的 `game/common` 定义：建筑、建筑组、商品、法律、机构、生产方式、生产方式组、科技、时代、defines和static modifiers。这样可以留下与该存档对应的游戏规则版本，避免用另一版本的定义解释存档。

这一步只导出定义键和文件哈希，不会替学生计算研究变量。若找不到 `game/common`，工具会停止，不会静默跳过。

## 工具生成什么

最新输出位于 `output_packages/V3_raw_export_日期_时间`，其中：

- `raw_data/save_metadata_raw.csv`：存档身份、哈希、版本和日期；
- `raw_data/country_scalar_fields_raw.csv`：国家人口统计和预算中的直接标量字段；
- `raw_data/country_trend_values_raw.csv`：GDP、平均生活水平、识字率等存档中的原始趋势值；
- `raw_data/budget_slots_raw.csv`：收入与支出槽位原值；
- `raw_data/pop_records_raw.csv`：比利时境内每条人口记录；
- `raw_data/building_records_raw.csv`：比利时境内全部建筑实体，不按工业篮子筛选；
- `raw_data/state_records_raw.csv`、`state_pop_statistics_raw.csv`：州记录及州人口统计原值；
- `raw_data/institutions_raw.csv`、`laws_raw.csv`：机构与法律原始记录；
- `raw_data/construction_queue_raw.csv`：保存时仍在政府或私人队列中的项目；
- `raw_data/game_definition_files_raw.csv`：本机相关游戏定义文件的路径、大小与SHA-256；
- `raw_data/game_definition_keys_raw.csv`：从本机 `game/common` 读取的顶层定义键；
- `game_environment.json`：游戏安装目录、Steam build、版本和定义总指纹；
- `manifest.json`：工具版本、文件哈希、游戏版本、日期和成功/失败状态；
- `export_log.txt`：完整运行记录；
- 一个内容相同、便于上传的 ZIP。

工具不会移动、改名或修改 `input_saves` 中的原始存档。

## 第一次使用

### Windows

1. 确认电脑安装了 64 位 Python 3.11 或更新版本；
2. 双击 `setup_windows.bat`；
3. 看到 `SETUP COMPLETE` 后关闭窗口。

### macOS

1. 确认电脑安装了 Python 3.11 或更新版本；
2. 打开“终端”，把终端切换到本文件夹；
3. 运行 `bash setup_macos.sh`；
4. 看到 `SETUP COMPLETE` 即完成。

如果不知道如何操作，可以把 `AI助手操作指令.md` 发给 AI，让它根据电脑实际画面逐步指导。

### 如果工具找不到 Victoria 3

打开本文件夹中的 `game_path.txt`，在最后一行填写 Victoria 3 安装根目录，也就是其中应当能看到 `game/common` 的文件夹。例如：

- Windows：`D:\SteamLibrary\steamapps\common\Victoria 3`
- macOS：`~/Library/Application Support/Steam/steamapps/common/Victoria 3`

不要填写到 `game/common` 下面的某一个具体文件。

## 每次导出

1. 退出或暂停游戏，确保存档已写完；
2. 将需要导出的 `.v3` 文件复制一份到 `input_saves`；
3. 不要把唯一的原始存档直接拖进工具；
4. Windows 双击 `export_windows.bat`；macOS 运行 `bash export_macos.sh`；
5. 打开 `output_packages` 中最新的 `V3_raw_export_日期_时间` 文件夹；
6. 检查 `manifest.json` 中 `failed_files` 是否为 0；
7. 检查每份存档的 `definition_version_match`；正式数据应为 `true`；
8. 上传最新 ZIP，并按老师要求另行保存或上传对应原始 `.v3`。

## macOS特别说明

Garibaldi官方没有附带macOS版原生解包程序，因此本工具的macOS路径只直接处理Debug模式产生的未压缩文本存档。

- 如果存档是未压缩文本 `.v3`，可以直接导出；
- 如果提示 compressed/binary，工具会停止，不会伪造成功结果；
- 保留该原始存档，把它交给Windows同学或老师的工具处理；
- 不要改扩展名、手动解压重压或覆盖原始存档。

## 每次提交必须保留

- 原始 `.v3` 文件；
- 工具生成的 ZIP；
- 游戏版本、checksum、DLC/mod状态截图；
- 若出现错误，保留整个输出文件夹和 `export_log.txt`。

## 不要做

- 不要修改 `tool` 文件夹中的程序；
- 不要让 AI 覆盖、重命名或删除原始 `.v3`；
- 不要只交 CSV 而不保留原始存档；
- 不要把空值或缺失值改成 0；
- 不要在“导出阶段”把自行计算的列写回这些 `_raw.csv`；
- 不要混用不同工具版本生成的数据。
