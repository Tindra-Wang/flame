# AI-07 火焰数据集建模

日常启动复用已准备的本地镜像，不访问Docker Hub；更新源码后追加 `-Rebuild` / `--rebuild`。首次下载/构建遇到EOF等网络错误会有限重试，持续失败时按部署文档检查Docker网络或代理。

## 快速开始：在自己的电脑运行平台

部署云服务器之前，其他人也可以在自己的电脑上运行平台，无需连接源码提供者的电脑。下载或解压源码后，进入包含 `start.ps1` 的项目根目录，在该目录打开 PowerShell。

### Windows 首次安装与启动

复制执行以下一条命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -InstallDocker
```

脚本会检查 Docker，缺少时通过 winget 安装 Docker Desktop，然后下载所需依赖、构建镜像并启动平台。无需自行安装 Python、Node.js/npm、PostgreSQL、FDS 或 Blender。首次安装需要联网；如果 Docker/WSL2 提示重启 Windows，重启后再次执行同一命令，并确保 Docker Desktop 使用 Linux 容器引擎。

启动成功后，在浏览器打开 **http://localhost:3000**。

首次使用时，在网页自行设置管理员用户名和密码，没有默认管理员密码；后续成员由管理员创建账户。

### NVIDIA GPU 模式

如需扩散增强、GPU 训练等功能，电脑需具备兼容的 NVIDIA 显卡、驱动及容器 GPU 支持。首次启动执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -InstallDocker -Gpu
```

已完成普通模式安装后，也可执行同一命令启用 GPU 模式。GPU 设置会保存，后续普通启动会继续使用 GPU Worker。默认 CPU 模式支持仿真、渲染、预览和审核；GPU 扩散增强及训练需要 GPU 模式。

### 后续启动与停止

以后启动，在同一项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

停止平台：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -Action Stop
```

停止会保留账户和数据。运行数据使用 Docker 命名卷，仍占用运行 Docker 的电脑磁盘空间；不要删除这些卷。

### 分享源码与已有数据

只分享源码，对方得到的是自己的全新平台，不会带上你的账户、上传文件和已有数据。如需使用已有数据，需要另外提供备份包并恢复；恢复后使用备份中的原账户登录。备份、恢复、Google Drive 的使用边界及迁移云服务器的步骤见[容器独立部署与云迁移](docs/容器独立部署与云迁移.md)。

Ubuntu/Debian 在源码根目录执行（已安装 Docker 时可省略 `--install-docker`）：

```sh
sudo sh start.sh --install-docker
```

GPU 模式追加 `--gpu`。当前容器引擎二进制面向 Linux x86_64；ARM 机器尚未验证。

下文保留旧宿主 Worker 部署和算法操作说明；新用户优先使用上面的根目录启动脚本，不要将两套 Compose 叠加启动。

受控合成已接入3D编辑页：FDS场复用 → 多条件Blender渲染 → SD1.5掩膜inpainting → 候选标注/审核 → 原有版本与导出。见[实现、操作与真实验证](docs/受控合成实现与验证.md)。ControlNet权重尚未安装，真实数据算法验收尚未完成。

完整平台目标设计、10张可编辑图、PERT/人力与资源成本、数据库和API预留契约见[软件设计与低成本实施方案](docs/design/软件设计与低成本实施方案.md)。这些是目标设计，现有代码的实现边界仍按下文说明。

本项目实现本地算法建模链：配置、FDS工况、渲染、增强、候选标注、质检、人工审核、版本导出及评价。各工具通过文件契约衔接。现已新增Vue3统一Web工作台、FastAPI应用服务、五角色账户权限、PostgreSQL任务队列、独立算法Worker、Label Studio对接、DVC真实发布及评价/验收页面。云端部署和完整算法验收仍需独立证据。

已准备Python虚拟环境；Compose按FDS、Blender、扩散增强、人工审核和评价划分运行环境。首次需要下载镜像和公开权重。运行步骤见[Compose建模指南](docs/Compose建模指南.md)，本机实跑记录见[验证结果](artifacts/compose-verified-v3/validation.json)。

## 统一可视化工作台

FDS时序参数、页内MP4、预测与训练数据的区分，以及基础渲染/受控增强的实现边界见[FDS时序与训练数据链路](docs/FDS时序与训练数据链路.md)。

完整3D编辑器的原版渲染/作业功能、Mantaflow与FDS执行路线、MP4进度及续跑见[原版编辑器迁移与执行链路](docs/原版编辑器迁移与执行链路.md)。

入口：**http://localhost:3000**。从场景配置、FDS/Blender/SD任务，到人工标注、DVC版本与COCO/YOLO导出，都在同一平台操作。

```powershell
powershell -File scripts/start-platform.ps1
```

首次访问可只读查看真实产物；创建自己的本地账户后操作。专用Label Studio在8082，原8080服务保留。详见[平台使用与部署手册](docs/统一平台使用与部署.md)和[开源参考与实现映射](docs/开源参考与实现映射.md)。本机版本不是已通过云端或算法最终验收的成品。

## 1 本机虚拟环境

在PowerShell进入项目目录。无需激活，也无需更改系统执行策略：

```powershell
cd D:\软件工程\AI-07
.\.venv\Scripts\python.exe -m fire_modeling doctor
.\.venv\Scripts\python.exe -m fire_modeling demo --output artifacts/demo-new --count 12
```

示例生成室内、室外两类场景，共32张原图及传统增强图，结果位于`artifacts/demo-new`。查看`contact_sheet.png`、`manifest.json`与`quality.json`。预览采用简化浮力粒子模型，属于程序化视觉预览，不是FDS求解、真实照片或扩散模型输出，所有标签均待审核。

需要激活时运行`.\.venv\Scripts\Activate.ps1`；若被PowerShell执行策略限制，继续使用上面的解释器完整路径即可。新环境可运行`scripts/setup.ps1`，或手动执行：

```powershell
$env:UV_CACHE_DIR = "$PWD\.cache\uv"
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.lock -e .
```

`requirements-dev.lock`固定了本次已安装的基础和测试依赖；GPU扩展在实际验证后另行锁定。不要把`.venv`提交到Git或复制进容器。

## 2 Docker Compose

Compose容器与宿主机`.venv`独立；全部建模阶段可在容器内运行。启动Docker Desktop的Linux引擎后，在项目目录执行：

```powershell
.\scripts\run-compose.ps1 -Stage Build -Mirror
.\scripts\run-compose.ps1 -Stage Doctor
.\scripts\run-compose.ps1 -Stage Generate -Run room-v1 -Count 2
.\scripts\run-compose.ps1 -Stage Review
```

`Build`构建镜像并下载校验FDS和固定版本Stable Diffusion 1.5；`-Mirror`仅切换依赖镜像源，网络正常可省略。`Generate`依次执行真实FDS、Blender Mantaflow和预训练模型增强，输出`artifacts/room-v1/`。任务型服务使用`run --rm`，结果保留在宿主机。输出目录非空时拒绝覆盖；可使用新的`-Run`或单独执行尚未开始的阶段。

各服务只通过配置和产物文件交换数据：

- `assets`：公开模型和引擎下载、断点续传与校验。
- `physics`：FDS仿真，交付HRR、切片、日志和带校验值的交接清单。
- `blender`：核对交接清单后执行流体烘焙、RGB与候选掩膜渲染。
- `enhance`：GPU执行真实img2img，保留父图、种子与权重哈希。
- `annotation`：本机8080端口的Label Studio；需人工注册、建项目和审核。
- `modeling`：标注导入、质检、版本冻结、COCO/YOLO导出与基础测试。
- `gpu`：共享扩散/评价环境，执行FID、YOLO训练及独立测试命令。

GPU容器需要WSL2及兼容NVIDIA驱动。公开SD1.5是通用生成模型，YOLO公开权重是通用检测初始化；火焰效果仍需真实数据验证。人工审核、真实数据FID和检测对照实验不会由脚本自动判定通过。

## 3 真实仿真与渲染

先检查配置，单独生成FDS工况：

```powershell
.\.venv\Scripts\python.exe -m fire_modeling prepare --config configs/room.json --output artifacts/room-input
```

安装FDS和Blender后，通过环境变量设置可执行文件位置，再执行真实路径：

```powershell
$env:FDS_EXE = 'C:\实际安装目录\fds.exe'
$env:BLENDER_EXE = 'C:\实际安装目录\blender.exe'
.\.venv\Scripts\python.exe -m fire_modeling generate --config configs/room.json --output artifacts/room-physical --physics fds --renderer blender --enhancer none --count 4
```

FDS运行结果保留输入、求解日志、HRR CSV及温度/烟密度/速度切片引用。适配器读取真实HRR并映射到Blender Mantaflow的燃料量；该路线是**物理量驱动的视觉代理**，不是将FDS三维场完整重建为火焰。Blender保存`.blend`、流体缓存、RGB和火焰发光候选通道。无火负样本是明确标记的视觉反事实，不冒充已经求解的无火FDS工况。

## 4 真实扩散增强

在本机虚拟环境中按所选GPU驱动安装兼容PyTorch，再安装项目扩展：

```powershell
$env:UV_CACHE_DIR = "$PWD\.cache\uv"
uv pip install --python .venv/Scripts/python.exe -e '.[diffusion]'
.\.venv\Scripts\python.exe -m fire_modeling generate --config configs/room.json --output artifacts/room-diffusion --renderer preview --enhancer diffusion --model-dir models/sd15 --device cuda --count 4
```

`models/sd15`应为已获授权、含`model_index.json`的本地Diffusers格式Stable Diffusion模型。代码不会自动下载模型；首次加载会计算权重哈希。上例仅验证真实扩散适配器，基础图片仍是预览；正式样本可同时设置`--physics fds --renderer blender`。图像增强后仅继承候选框，必须再次人工核对，不直接视为真值。

## 5 审核、发布与导出

查看图像后，逐个确认样本；框需要修改时，提供包含像素`[x0,y0,x1,y1]`列表的JSON，通过`--boxes-json`传入：

```powershell
.\.venv\Scripts\python.exe -m fire_modeling review --run artifacts/demo --sample room_demo_00001 --reviewer 你的姓名
.\.venv\Scripts\python.exe -m fire_modeling publish --run artifacts/demo --output artifacts/version-v1 --version v1
.\.venv\Scripts\python.exe -m fire_modeling export --version-dir artifacts/version-v1 --output artifacts/export-v1
```

只发布实际审核通过的样本；父图通过不代表增强图通过。旧版本复制图像并冻结标签、审核修订和源清单，修改原始运行目录不会改动已发布版本。导出包括YOLO、总体及分集合COCO、类别映射、数据卡与SHA-256清单。少量独立来源组可能导致val/test为空，不能拆开同源组凑比例。

可通过`label-studio`命令导出预标注任务，使用`configs/label_studio.xml`作为标签配置；图像URL必须指向你有权访问的实际服务。人工完成后，用`import-label-studio`导入标注导出文件。系统不会把`predictions`当作人工审核。

## 6 算法评价

- `distribution --real 真实图像目录 --synthetic 合成图像目录 --metric fid --dims 64 --output artifacts/fid.json`：真实Inception FID，需要`.[evaluation]`和Inception权重；特征权重首次可能由库下载。两个目录直接放待比较图片，固定数量和抽样方式。
- `--metric color-js`：可在基础环境运行的RGB直方图JS距离，**不是FID**。不能将其换成“相似度百分比”。
- `physical-error --reference 实测序列.json --prediction 仿真序列.json --output artifacts/physical.json`：计算同物理量、同单位、覆盖相同时间段的归一化绝对误差。序列包含`quantity`、`unit`、`time_s`和`values`，不自造实测参照。
- `detection-metrics --truth COCO.json --predictions 预测.json --output artifacts/detection.json`：读取像素xywh预测框和置信度，计算单类AP50、AP50-95、Precision、Recall和负样本误报；不等同于含全部COCO特殊规则的官方评估器。
- `train-color`与`predict-color`：实现可学习的弱框监督逻辑回归颜色基线，用于验证训练、模型保存和预测闭环，**不是YOLO**。
- `train-yolo-pair --spec configs/yolo_experiment.example.json --output artifacts/yolo-pair`：真实YOLO训练和独立真实测试集对照，需要`.[evaluation]`、本地权重及准备好的真实/混合数据集。校验两组共享验证/测试数据、训练测试精确重复，并对齐训练图片列表长度；结果记录实际迭代数，不同预算时不作效果结论。

真实数据可用`import-coco`导入，需提供`--source-url`和`--license-note`，标准单类COCO类别为`id=1,name=fire`。建议在COCO每个image记录中补充事件`group_id`；未提供时保守地把整个导入放在同一组。导入标签仍需确认。`merge-runs --runs 真实运行目录 合成运行目录 --output 新目录`合并来源及审核记录，再发布混合版本。事件/近重复泄漏仍需人工复核，文件哈希检查无法替代它。

## 7 测试与模块

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

代码划分：`config`参数；`physics`物理工况；`procedural`CPU预览；`blender_adapter/blender_scene`独立渲染；`enhancement`增强；`annotations/quality`候选标签与质量；`dataset`审核及版本；`evaluation`模型与指标；`pipeline/cli`只负责编排。核心代码不导入外部引擎，重型依赖按需加载。

渲染通过`adapters.Renderer`契约接入，流水线可注入替代实现，不依赖Blender内部对象。任务和模型均通过配置及文件结果交接。

完整数学假设、输入输出和验证边界见[算法建模说明](docs/算法建模说明.md)。


独立物理仿真入口：http://localhost:3000/#simulation 。已接入FDS 6.11.1及fdsreader 1.14.0，支持温度、烟炱密度、速度切片及时间播放；API与边界见[火焰仿真接入](docs/火焰仿真接入.md)。


FirePhantom已导入`integrations/firephantom`，以独立Linux服务接入主平台“火焰仿真”页。运行`./scripts/start-firephantom.ps1`；原始目录保持不变。该独立服务是早期接入入口；当前主要操作使用平台3D编辑器及FDS→OpenVDB→Blender原生链路。详见[接入与能力核对](docs/FirePhantom接入与能力核对.md)。

## 主平台内的统一火焰链路

访问 http://localhost:3000/#simulation，在同页配置FDS、查看三维场渲染火焰，进入候选审核与DVC导出。无需登录第二套FirePhantom平台。完整操作、文件契约与实测边界见[统一火焰链路](docs/统一火焰链路.md)。已有引擎更新代码运行 `./scripts/update-engines.ps1`，然后 `./scripts/start-platform.ps1`。

完整三维编辑已恢复：[三维场景编辑与FDS交接](docs/三维场景编辑与FDS交接.md)。主仿真页选择场景后打开编辑页，保存模型、燃烧物、结构、相机和灯光，再返回运行FDS→Blender。

完整三维场景编辑、保存返回与FDS/Blender接入说明： [3D场景编辑接入](docs/3D场景编辑接入.md)。

页内连续审核、Label Studio后台同步、审核后分布快照与版本化检测A/B接口见[合成审核与评价闭环](docs/合成审核与评价闭环.md)。真实检测收益需独立真实数据实跑。
