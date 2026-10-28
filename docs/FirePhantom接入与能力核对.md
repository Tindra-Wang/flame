# FirePhantom 独立接入记录

> 本文记录早期8765独立服务方案。当前主入口已经改为原平台内的统一FDS/OpenVDB/Blender/SD链路，详见[统一火焰链路](统一火焰链路.md)。下文“尚未解决”是上游源码的判断，不是本次主平台适配后的最终状态。

源目录：`D:/软件工程/FirePhantom/FirePhantom`。导入目录：`AI-07/integrations/firephantom`。原始目录未修改。导入文件清单与SHA256在`integrations/firephantom-import.json`。源项目带有独立SRS；本次不覆盖AI-07根目录SRS，也不把两套验收阈值混用。

## 接入方式

采用独立服务集成，保留Vue主平台及原FDS路线。FirePhantom继续运行自己的React/FastAPI、Blender、PostgreSQL和数据卷，主平台通过状态检查与HTTP跳转提供入口。接口连接的是运行服务，不是直接执行一个GitHub目录。

- 主平台入口：`http://localhost:3000/#simulation`，点击“打开FirePhantom”。
- `GET /api/integrations/firephantom`：检查服务是否在线并说明集成边界，不转发用户凭据。
- `GET /api/integrations/firephantom/open`：服务在线时307跳转到固定的`http://localhost:8765/`；离线时返回503及启动提示，不接受任意跳转地址。
- FirePhantom作业接口：`POST /api/v1/jobs`，状态为`GET /api/v1/jobs/{id}`。
- FirePhantom背景增强：`POST /api/v1/datasets/{id}/sd-augment`；要求已审核的原始样本。
- 当前两边账户、作业、样本及DVC版本仍独立，不做单点登录或样本自动互认；未审核图像不自动灌入原平台已审核集合。

本机运行端口8765仅绑定127.0.0.1，数据库不向主机暴露端口。其`fcntl`依赖由Linux容器承载，避免直接在Windows导入失败。复用已安装Blender镜像；补足原requirements未声明的python-multipart。前端在本机构建后COPY入镜像，不复制node_modules，也不重新下载Blender。Blender和渲染主路径使用CPU；SD仍需单独配置可用的兼容服务。

启动：

```powershell
cd D:/软件工程/AI-07
./scripts/start-firephantom.ps1
# 已构建镜像后，仅启动、不重新安装依赖：
./scripts/start-firephantom.ps1 -SkipBuild
```

首次进入FirePhantom由用户创建自己的管理员账户；本次不替用户设置密码。源码中部分作业/文件接口未统一校验登录，本次在`docker/firephantom_entry.py`外层补充会话门禁与写入Origin检查，导入源码保持不变。统一主平台的普通启动脚本仍不强制启动此较重服务。

## 解决或改善的问题（源码证据）

1. 场景不再只有固定空房间：提供React Three Fiber三维编辑器，燃料摆放、相机、灯光、气体域和结构可调整，并有场景版本。
2. 固定单帧改为时间序列：同天气烘焙一次，复用给多个真实相机和连续帧，并有渲染缓存。见`physics/engine.py`与`physics/blender_scene.py`。
3. 体积材质有所改善：设置温度/热场映射、黑体色、烟密度、体积反弹与降噪，提供流体噪声、分辨率16–128和采样8–256的可调项；改善不等于已经证明照片级质量。
4. SD不再默认整图改火：`synthesis/sd_augment.py::restyle`膨胀火焰掩膜后只请求修改外部区域，合成后验证保护区像素完全一致；只对已审核样本做背景重绘。
5. 候选标签更丰富：有火焰、烟、火星掩码和序列分组；支持标注、质量筛除、导出与版本流程。

## 尚未解决的问题（不能宣传为已完成）

1. **没有FDS→三维物理场→Blender交接。**`normalize_fire_engine`只接受blender；`engine.py`始终调用`compute_fields`，并把`physical_backend`写为`parameterized-plume`。这些温度/烟/速度网格不是FDS输出，也不是从Mantaflow缓存回读。原平台FDS路线必须保留。
2. **物理参数未完成独立校准。**燃料HRR/烟炱来自内置表；未知燃料甚至使用名称哈希生成参数。天气、湿度、燃烧蔓延主要是规则与视觉近似，不能据此声明CFD物理误差合格。
3. **清晰度仍有硬限制。**Blender输出固定256×256，`engine.py::_read_png`也强制调整到256；SD请求同样固定256。渲染默认20采样，虽可调但不会自动成为高分辨率数据集。背景重绘保护火焰，同时也保留原来火焰已有的模糊。
4. **像素保护不等于完整标签正确。**背景仍可能出现新的伪火、遮挡或语义变化；派生样本自动继承审核和框，尚缺独立复审/额外火焰检测。掩膜保护不是ControlNet深度约束，也不是FLAME Diffuser算法移植。
5. **仍需真实数据的检测对照。**FID/IS在无Inception权重时回退到确定性嵌入及4类分类头；这些回退值不等同于标准FID/IS。没有权重与真实测试集时不能用于算法验收。
6. **依赖缺失会触发回退。**Blender失败时仍可能返回参数化投影图；须检查`renderer`和`engine_frames_source`，不能只看HTTP 200。场景资产目录、SD、Label Studio和参考集也需要实际配置与验证。

## 接入边界与下一步

本次是可运行入口与服务集成，不是将两套数据模型合成一套。推荐先保持“FDS物理观察”和“FirePhantom视觉合成”并列，再建立统一场景/相机契约与数据导入审核门禁；之后做FDS三维场转换和受控增强评价。不能把两个页面间的跳转当作算法耦合完成。

Label Studio尚未自动绑定原平台项目，避免误写已有标注任务；SD端点当前预留为宿主机7861兼容服务，未配置时必须显示失败。原目录的macOS外置盘资产和模型不会自动出现在本机容器里。本次联调和测试的实际证据见`artifacts/platform/firephantom-verification.json`，未执行项不得记成通过。

## 本次实测（2026-10-21）

服务已启动：健康检查200，主平台跳转307，未登录读取作业401。首次管理员尚未创建，由使用者自行设置。新增部署门禁、状态探测与固定跳转测试后，AI-07自动化测试72项通过，覆盖率81.11%（fire_modeling、platform_api及docker适配层）；未执行FirePhantom整套上游测试。

实际运行两组小场景，每组两帧，均返回`renderer=blender`，未触发图片回退；物理场仍为`parameterized-plume`。最低渲染配置耗时3.96秒，源码默认配置（预热1秒、噪声2、20采样）耗时9.18秒，仅代表本机该小场景。默认图像见`artifacts/platform/firephantom-default-render.png`，仍为256×256且火焰偏软，不能据此声明清晰度问题已解决。

火焰保护与背景合成函数验证通过；本次没有执行FirePhantom的真实SD模型，也没有验证其Label Studio绑定。原平台此前的SD/标注联调证据不能替代此独立服务的验证。
