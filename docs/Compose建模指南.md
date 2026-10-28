# Compose建模指南

所有命令在`D:\软件工程\AI-07`执行。Docker Desktop使用Linux容器；GPU阶段需要NVIDIA GPU。容器不依赖宿主机Python虚拟环境。

## 一次性准备

```powershell
.\scripts\run-compose.ps1 -Stage Build -Mirror
.\scripts\run-compose.ps1 -Stage Doctor
.\scripts\run-compose.ps1 -Stage Test
```

`-Mirror`为网络较慢时使用的HTTPS依赖镜像源。默认源仍是PyPI和Debian官方源。首次下载数GB镜像及模型，准备足够磁盘空间。文件放在`models/`、`engines/`，不提交Git；支持模型断点续传、权重SHA256校验。单独下载可运行`docker compose run --rm assets`。

固定模型：`stable-diffusion-v1-5/stable-diffusion-v1-5`，revision `451f4fe16113bff5a5d2269ed5ad43b0592e9a14`，fp16 safetensors，保留安全检查器。模型卡、配置及下载来源保存在模型目录。使用时遵守CreativeML Open RAIL-M许可。FDS固定6.11.1；Blender固定官方4.5.3 LTS便携版，两者均校验官方发行包摘要。Debian版Blender4.3.2经实测存在Mantaflow/Python初始化崩溃，已替换。

## 生成候选数据

```powershell
.\scripts\run-compose.ps1 -Stage Generate -Run room-v1 -Config room.json -Count 2
```

流程：参数校验 → FDS → Blender流体烘焙及渲染 → 扩散增强 → 候选标注与质检 → 导出审核任务。

各阶段通过文件交接，分别保存在`artifacts/room-v1/physics`、`render`、`enhanced`。FDS配置或HRR哈希不符会停止；增强前核对源图哈希。失败不降级为程序化预览，失败目录不覆盖。可用`-Stage Simulate`、`Render`、`Enhance`执行单一阶段；已经失败的阶段应检查日志并换新运行目录。

FDS的HRR驱动Mantaflow燃料量属于视觉代理，尚未把FDS温度、烟密度、速度三维场完整导入Blender。无火图为明确标记的视觉反事实。扩散后的框仅是待复核候选，不能直接当真值。

## 人工审核与导出

```powershell
.\scripts\run-compose.ps1 -Stage Review
```

`Review`会启动Docker Desktop、等待Linux引擎就绪，再启动审核服务并检查健康状态。打开`http://127.0.0.1:8080`（也可用`http://localhost:8080`），首次注册本机账号；创建项目，标签配置复制`configs/label_studio.xml`，导入`artifacts/room-v1/review-tasks.json`。重启电脑或退出Docker后，需要重新执行`Review`。本地图像根目录在容器内为`/data/artifacts`；如界面要求存储配置，添加该根目录下的Local Files源。逐张修正框并提交，包括无火负样本。导出JSON到`artifacts/room-v1/reviewed.json`，再执行：

```powershell
.\scripts\run-compose.ps1 -Stage Finish -Run room-v1 -Tasks /app/artifacts/room-v1/reviewed.json -Reviewer 你的姓名
```

只发布审核通过样本，输出冻结版本`version/`及COCO/YOLO数据`export/`。同一FDS工况及其增强后代放在同一数据划分中；两个样本仅供链路验证，不足以建立有效train/val/test。

## 算法评价

容器内所有路径以`/app/`开头。准备真实图像后：

```powershell
docker compose run --rm gpu distribution --real /app/artifacts/real-images --synthetic /app/artifacts/room-v1/enhanced/images --metric fid --dims 64 --output /app/artifacts/fid.json
docker compose run --rm gpu train-yolo-pair --spec /app/configs/yolo_experiment.compose.json --output /app/artifacts/yolo-pair-v1
```

`Build`同时准备FID Inception权重到持久缓存；若未执行准备则由库首次下载。64维FID需明确报告维度，不能与2048维结果直接比较。YOLO示例配置需要先建立真实与混合数据集，二者共用独立真实val/test且训练预算一致。公开YOLO11n权重仅为初始化，不是已经训练好的火焰检测器。没有真实数据时，不生成检测收益、FID真实性或物理精度通过结论。

## 运行边界

这是本地批处理建模链及审核工具，不包含完整业务Web平台、多人权限系统、K8s或云部署。`docker compose stop annotation`停止审核服务，数据卷保留。无需清理其他项目镜像或容器。

参考：[Docker GPU编排](https://docs.docker.com/compose/how-tos/gpu-support/)、[FDS发行包](https://github.com/firemodels/fds/releases/tag/FDS-6.11.1)、[SD1.5模型卡](https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5)、[YOLO11权重](https://github.com/ultralytics/assets/releases/tag/v8.3.0)、[pytorch-fid](https://github.com/mseitzer/pytorch-fid)、[Label Studio本地存储](https://labelstud.io/guide/storage.html)。
