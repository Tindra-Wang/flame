---
name: 焰序 · AI-07 火焰数据工作台
description: 以实际产物和来源为中心的科研图像接触印相台
colors:
  canvas: '#f9f3e9'
  paper: '#fffdf9'
  ink: '#2b2015'
  muted: '#8d7c66'
  faint: '#b4a18a'
  line: '#ecdfca'
  line-2: '#f2e7d6'
  orange: '#d9480f'
  orange-hover: '#bf3208'
  ember-gradient: 'linear-gradient(100deg,#f08a3c,#d9480f 55%,#bf3208)'
  green: '#3f9d63'
  soft: '#f8ecdc'
  surface-2: '#f7ecdd'
  sidebar: '#31241a'
  nav-selected: 'linear-gradient(90deg,rgba(240,138,60,.20),rgba(217,72,15,.05))'
  pending-bg: '#fbe9d2'
  pending-text: '#a35a12'
  approved-bg: '#e2f0e4'
  approved-text: '#2f7d4d'
  failed-bg: '#fbe3dc'
  failed-text: '#b03311'
  running-bg: '#e3ecf5'
  running-text: '#4a7ba6'
  card-shadow: '0 8px 24px rgba(150,90,40,.12)'
  primary-glow: '0 8px 22px rgba(217,72,15,.32)'
  editor-bg: '#1d1d1d'
  editor-panel: '#303030'
  editor-header: '#262626'
  editor-widget: '#3d3d3d'
  editor-text: '#d4d4d4'
  editor-accent: '#4772b3'
  scientific-viridis-0: '#440154'
  scientific-viridis-25: '#3b528b'
  scientific-viridis-50: '#21918c'
  scientific-viridis-75: '#5ec962'
  scientific-viridis-100: '#fde725'
typography:
  headline:
    fontFamily: 'IBM Plex Sans, Noto Sans SC, Microsoft YaHei, sans-serif'
    fontSize: '31px'
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: '-0.01em'
  title:
    fontFamily: 'IBM Plex Sans, Noto Sans SC, Microsoft YaHei, sans-serif'
    fontSize: '19px'
    fontWeight: 700
    lineHeight: 1.45
  body:
    fontFamily: 'IBM Plex Sans, Noto Sans SC, Microsoft YaHei, sans-serif'
    fontSize: '14px'
    lineHeight: 1.8
  label:
    fontFamily: 'IBM Plex Sans, Noto Sans SC, Microsoft YaHei, sans-serif'
    fontSize: '13px'
    fontWeight: 500
    lineHeight: 1.7
  metric:
    fontFamily: 'IBM Plex Sans, Noto Sans SC, Microsoft YaHei, sans-serif'
    fontSize: '34px'
    fontWeight: 650
    lineHeight: 1.2
rounded:
  tag: '5px'
  control: '9px'
  image: '10px'
  panel: '12px'
spacing:
  tight: '8px'
  control: '12px'
  standard: '16px'
  group: '20px'
  section: '24px'
  wide: '26px'
motion:
  fast: '120ms'
  standard: '200ms'
  slow: '320ms'
  easing: 'cubic-bezier(.2,.7,.3,1)'
components:
  button-primary:
    backgroundColor: '{colors.ember-gradient}'
    textColor: '{colors.paper}'
    typography: '{typography.label}'
    rounded: '{rounded.control}'
    padding: '10px 16px'
    shadow: '{colors.primary-glow}'
  button-primary-hover:
    transform: 'translateY(-1px)'
    shadow: '{colors.primary-glow}'
    filter: 'brightness(1.05)'
  button-primary-active:
    transform: 'scale(.97)'
  button-secondary:
    backgroundColor: '{colors.paper}'
    textColor: '#5a4630'
    borderColor: '#e3d2b6'
    typography: '{typography.label}'
    rounded: '{rounded.control}'
    padding: '10px 16px'
  field:
    backgroundColor: '{colors.paper}'
    textColor: '{colors.ink}'
    borderColor: '#e3d2b6'
    rounded: '{rounded.control}'
    padding: '9px 12px'
  panel:
    backgroundColor: '{colors.paper}'
    rounded: '{rounded.panel}'
    padding: '26px'
    shadow: '{colors.card-shadow}'
  badge-pending:
    backgroundColor: '{colors.pending-bg}'
    textColor: '{colors.pending-text}'
    rounded: '{rounded.tag}'
    padding: '4px 7px'
  nav-selected:
    backgroundColor: '{colors.nav-selected}'
    indicator: '3px ember-gradient bar on the left edge'
    textColor: '{colors.paper}'
    rounded: '{rounded.control}'
    padding: '13px 14px'
---

# Design System: 焰序工作台

## Overview

**Creative North Star: "科研图像接触印相台"**

**视觉判断（一句话）**：蜜蜡暖纸上的白面板靠色阶分层、不靠描边；一支焰橙只给当前态与动手的地方；数字永不跳宽；工具动效瞬时、成功反馈才弹。

Operate 模式。蜜蜡暖纸承载图像、来源和审核操作，深咖啡导航提供稳定坐标，焰橙渐变标记主要动作。密度服务于实际操作：先看产物，再检查参数、修订标注与发布版本。

图像来自实际生成产物，模拟与增强来源始终可见。数字、状态和曲线对应可追溯记录；缺少真实参照数据或独立评价时，显示空值和原因。

**Key Characteristics:**
- 蜜蜡暖纸面与低饱和暖棕。
- 焰橙渐变只用于主要动作、品牌标与选中指示，不作为信息底色。
- 真实图像、来源与审核状态组成接触印相式浏览。
- 紧凑分组、清晰分隔、直接操作。
- 证据先于成绩。

## Colors

### Primary

焰橙 `orange` 用于主要操作、选中标签页、键盘焦点和已有求解曲线；主要按钮与品牌标使用 `ember-gradient`，悬停抬升并带 `primary-glow` 辉光，按压回缩（scale .97）。文字态悬停使用 `orange-hover`。

### Secondary

深咖啡 `sidebar` 建立导航底色，选中项用 `nav-selected` 渐变底加左侧 3px 渐变指示条。研究绿 `green` 保留为语义色。通过、发布和成功共用低饱和绿色；等待为琥珀，失败为焰红，运行为蓝灰。状态始终附文字。

独立三维编辑页保留 FirePhantom 原有深色工作区：`editor-bg`、`editor-panel` 和 `editor-header` 区分视口、属性面板与工具栏，`editor-widget` 承载紧凑控件，`editor-text` 保持文字可读，`editor-accent` 表达活动工具与选中项。此组颜色仅用于编辑页。

### Neutral

蜜蜡暖纸 `canvas` 是页面底色，`paper` 是表单、流程与编辑面板；`ink` 是主文字，`muted` 是说明，`line` 是分隔，`surface-2`/`soft` 是弱化底层，`faint` 是最弱元数据。实际值以 frontmatter 为准。

**The Evidence Rule.** 图像、数字、曲线和状态必须对应实际记录；未获得的评价显示空值和缺失原因。

**The Scientific Scale Rule.** 物理量连续色标使用 Viridis 五点（scientific-viridis-0 / 25 / 50 / 75 / 100），依次对应归一化数值从低到高；格点与色标使用相同插值。每个物理场以自身全时段最小值与最大值固定尺度，并明确该场单位；切换时间帧不重新归一化。此渐变是实际数据编码，仅用于物理量连续色标，不作装饰或状态色。

## Typography

IBM Plex Sans 与 Noto Sans SC 承担中英文字体，离线回退 Microsoft YaHei 和 sans-serif。标题和正文采用同一家族，以字重、大小和空间建立层级。

**The Type Floor Rule.** 全平台禁止 <11px 文字。固定三档：正文 14px；辅助与说明 13px（context-note、表单标签、面包屑）；元信息 12.5px 以下至 11.5px 地板（徽章 11.5px、时间戳 12px、图表刻度 12px、表格脚注 11px）。层级靠字号、字重与灰度对比表达，不靠新增更小的字。

页面标题采用 `headline`（700 字重、微收字距），移动端为（24px）；分区标题采用 `title`，移动端为（17px）。正文基准采用 `body`，操作与表单标签主要采用 `label`（13px）。说明类文字 12.5–13px。现有更小的紧凑元数据不视为未来正文标准。

指标采用 `metric`（650 字重），移动端为（29px），数字使用 tabular-nums。日志使用 Consolas / monospace（12px / 1.8）；哈希与提交号可使用等宽字体，普通业务文字不使用等宽字体。

独立仿真新增辅助文字与时间输出采用（12px），时间数值采用 tabular-nums；标题与单位小字沿用既有标题、紧凑文字样式，不改写全局字阶。

## Layout

桌面固定导航宽（228px），顶栏高（73px）；内容最大宽（1720px），常规内边距（36px 38px 25px）。原种子的 8px 节奏落地为多档间隔，按任务关系使用 frontmatter 中实际间距，而非强制单一倍数。

总览图像桌面四列、普通样本三列；卡片依次提供图片、来源、简短标题、状态与编号。六阶段流程按顺序排列。表单与说明、图像与坐标控制采用双栏。

（1200px）以下导航收至（208px）并缩小边距；（950px）以下总览为两列、流程为三列两行、编辑及主要表单为单栏；（720px）以下导航为带遮罩抽屉，顶栏高（62px），内容左右边距（18px），图像保持两列，指标三列换行。宽表格局部横向滚动。（1650px）以上增加顶部与流程留白。

**The Image Integrity Rule.** 浏览缩略图可以裁切；原图对比和标注编辑必须保留完整图像及其坐标比例。

**The Physical Coordinate Rule.** 二维物理场保留完整 XZ 切片，显示宽高比取实际 x、z 坐标跨度之比，两个方向的物理长度采用相同比例；z 向上、x 向右，轴向和固定 y 切片位置明确标注米。响应式缩放不得裁切或拉伸物理坐标。

独立仿真沿用 Operate 工作区：工况与求解结果双栏，窄于（1100px）时堆叠；延续现有纸面、细边线、控件与分组间距。

统一火焰工作台在原平台内串联"3D布景与仿真MP4 → 生成数据 → 标注与质检 → 版本与导出"；总览的六项技术链路继续保留。主页面上方提供场景选择和编辑入口，下方桌面左侧为仿真来源、样本数与 SD 增强配置，右侧为当前场景的数据批次；（900px）及以下改为单栏。主页面不重复展示编辑器中的视频或大图轮播。

独立三维编辑页保留原 React SceneWorkstation 的密集布局：桌面以三维视口为主，右侧上方为大纲，下方为属性侧栏，下方资产架提供模型浏览，区域间保留原分隔。属性侧栏沿用对象、场景、渲染、作业及补充链路标签；渲染参数与作业结果在对应标签内滚动。结果使用原版右侧抽屉，覆盖部分视口。窄屏沿用原布局的响应式堆叠，顶部操作换行；（760px）及以下增加视口和侧栏最小高度并随页面滚动。主平台保持暖纸面批次管理布局，同时显示编辑器提交的作业。

## Elevation & Depth

常规面板使用 `card-shadow` 轻悬浮；总览流程、表单面板、任务详情与版本行同档。主按钮使用 `primary-glow`，仅悬停增强。浮动反馈 toast 使用（0 10px 30px rgba(70,40,15,.35)），登录对话框使用（0 18px 50px rgba(80,50,20,.28)）。模态遮罩压暗背景，集中当前操作。

## Shapes

状态标签采用 `tag`，按钮与输入采用 `control`，图像采用 `image`，常规面板采用 `panel`。细线承担结构分组。标注框保持直角与图像坐标一致：普通框焰橙，活动/绘制框亮橙。

## Components

### Buttons

主要按钮焰橙渐变底白字，悬停抬升＋辉光，按压回缩；次要按钮纸白底暖棕字与细边线，最小高（40px）；紧凑变体最小高（32px）。次要按钮悬停抬升、底色与边线加深。文字按钮用于辅助入口。禁用透明度（0.55），显示等待光标。键盘焦点为焰橙外轮廓（2px，偏移3px）。SVG 线条图标配文字或可访问名称。

### Inputs / Fields

白底细边线、轻圆角、最小高（40px），悬停加深边线，聚焦显示焰橙描边光圈，标签紧邻字段。坐标输入为紧凑尺寸（最小高32px），具备逐框逐坐标的可访问名称。复选与单选使用焰橙选中态。

### Navigation

深咖啡底，纵向文字与线条图标。选中为焰橙渐变浅底白字加左侧渐变指示条，悬停右移（3px）并提亮，不替代选中含义。移动端展开相同导航。侧栏底部工作进程在线状态点带呼吸脉冲。

### Chips

小面积浅底与语义文字，无阴影。等待、通过、失败、运行和中性状态都保留明确文字。

### Cards / Containers

表单、任务详情与编辑面板使用纸白底细边线加轻阴影。图像卡片文字区开放，不额外嵌套卡片。常规缩略图宽高比（1.3），移动端（1.05）；悬停整卡抬升、图像放大（1.03倍），查看操作在悬停或键盘聚焦时显现。

### Review Editor

增强样本先并排展示完整原图与增强图，再展示画框区与坐标控制。对比图使用 contain；画框 SVG 跟随原始图像尺寸。支持指针绘制，也提供"添加火焰框"及数值坐标操作。恢复候选、通过审核与剔除职责分明，保留"候选框不是人工真值"的说明。

边线与显示操作过渡（120ms），页面切换与抽屉（200ms），缩略图缩放（320ms），统一缓动 cubic-bezier(.2,.7,.3,1)。页面切换带淡入上移入场；任务阶段"执行中"带呼吸脉冲；总览 HRR 曲线入场描画。遵守 prefers-reduced-motion，关闭全部动画与过渡。

### Simulation Field & Time Controls

物理场按钮同时标明场名和单位，选中态结合文字与 aria-pressed。色标标出固定上下限与单位，当前帧范围另行说明；热释放率曲线标明时间与 kW，求解器切片和渲染图像保持来源区别。

**The Time Frame Rule.** 时间滑块按求解器帧索引选择，旁边显示实际时间与秒单位；播放与暂停有可访问名称。切换试验或物理场时停止播放并复位，读取帧期间显示等待状态，播放只在当前帧已读入时推进；末帧后循环。

### Unified Flame Workbench

沿用原平台的账户、任务、批次和样本；提交、阶段日志、人工审核与版本发布保持同一数据链路。布景、引擎选择、视频渲染、作业日志和 MP4 播放集中在三维编辑器。主页面按场景选择当前保存版本已完成的仿真来源（source_simulation_id），配置样本数及可选 SD 增强，并管理合成批次；复用该仿真的 FDS 场与保存场景。当前版本无已完成仿真时显示原因并禁用生成。编辑器作业同时进入主平台任务管理，沿用认证、场景修订和产物记录。批次的审核和版本导出入口携带当前批次。

**The Submitted Batch Rule.** 提交后轮询当前场景的作业与批次，显示真实状态、错误和阶段日志入口；取得该任务的结果批次后，审核与导出入口携带其 run_id。不能用历史产物替代新任务成功状态；SD 模型拒绝或增强失败保留真实结果与原因。

**The Unified Provenance Rule.** FDS 三维场经 OpenVDB / Blender 的原始渲染、历史 HRR 视觉代理和 SD 增强保留各自来源；明确网格限制、光学材质未标定、视觉雾天非 FDS 湿度模型、关闭体积的视觉负例非无火 CFD 工况。数据集样本可能切换视角或天气，不能称为固定相机视频。MP4 按各保存机位分别输出，逐个真实求解时刻渲染，并标明机位、求解时段和采样说明。独立增强修订另存为待复审产物，保留父图与已有人工审核，不能覆盖已审核样本；增强图需重新审核。

### Original 3D Scene Editor

从主页面直接进入 `/scene-editor/index.html?project=…&scene=…`，使用同一主平台账户。页面导入原 SceneWorkstation，保留视口工具、大纲、属性、资产架、模型与燃料设置、起火点、结构、相机和灯光；顶部明确显示场景、修订与保存状态，提供"保存场景""渲染设置"和"作业与结果"入口；返回主平台仍携带同一项目与场景。

编辑页沿用原深灰控件和蓝色活动态，正文与标签以（12px）为主，按钮高（24px）、圆角（3px）；原版组件与样式是编辑器的视觉依据。资产架现有（161）项定义，其中（5）项为内置程序简模，缺失原网格的资产显示燃料盒；上传 GLB 后可显示实际网格。

渲染标签复用原版 GenerationSettings，先选择原版 Blender / Mantaflow 或 FDS 三维场 → Blender，再设置仿真与输出。Mantaflow 保留原版天气、湿度、燃烧物、气体域及预热、涡度、噪声等完整视觉模拟控件；FDS 使用真实物理场，明确说明未标定的湿度、雨雪及等效燃料限制，不支持的参数必须给出拒绝原因。未保存修改先保存再提交，作业绑定保存修订。

作业标签直接复用原版 SceneRuns 与 JobDetail，按当前场景展示作业、状态、进度、日志及可用动作。进行中作业使用缓存进度与心跳，离线或心跳过期明确警告；执行超时（30分钟）呈现真实失败原因。

### Original Result Drawer

组合结果直接复用原版 ComboDrawer：右侧白底抽屉保留组合标题、关闭动作、帧图与 MP4 并排预览、掩膜和框显示开关、帧缩略图多选、全部可送审选择、选中送审及仅重跑该组合。视频沿用抽屉内原生播放控件。主平台的审核与版本入口继续携带对应任务或批次；送审保持待审核状态。视频输出帧直接属于同一候选批次，避免为送审重新渲染。

**The Original Editor Rule.** 保留原版三维编辑器、渲染设置、作业详情与组合抽屉的视觉和交互结构。通过项目适配层连接主平台账户、任务与保存修订；上游组件源码保持原样。

**The Scene Continuity Rule.** 编辑与仿真共享保存场景；保存失败保留错误状态，不能宣称成功或返回后用其他场景替代。主平台与原三维编辑器各自保留既有视觉体系。

## Do's and Don'ts

### Do:
- **Do** 保留真实产物、来源、审核状态和可追溯编号。
- **Do** 用纸面、细分隔线与低饱和状态底色组织密集信息。
- **Do** 保持完整图像与标注坐标比例一致。
- **Do** 保留清晰键盘焦点，为图标操作提供可访问名称。
- **Do** 把焰橙渐变留给主要动作与选中指示，保持克制。

### Don't:
- **Don't** 把候选、程序预览或增强图标成真实火灾采集数据。
- **Don't** 虚构成绩填充缺失指标，或把求解曲线当作独立精度验证。
- **Don't** 用营销首屏替代实际工作区。
- **Don't** 依靠颜色单独表达审核或任务状态。
- **Don't** 让动效干扰读数：数字、日志和状态文字不做持续动画。


## 作业操作精简（2026-10-23）
编辑器顶部直接开始作业，作业标签保留同一提交入口；无需跳转。原生页内登录保留参数。任务中心每页8条紧凑列表，搜索/状态筛选；详情优先阶段、视频、样本与恢复操作，原始日志按需展开，不删除历史数据。


## FDS时序呈现（2026-10-23）
编辑器默认FDS，默认20秒/24时间采样。作业标签先选当前作业，再页内展开MP4和物理时轴；原版分组/帧/审核折叠保留。播放时按编码时间映射源场物理时间，展示真实FDS参数和明确标注的未训练因果外推。参数定义及训练导出说明按需展开；不将光学增强或重复视频帧标作新物理真值。

## 受控合成（2026-10-23）
原3D编辑器增加"数据合成"标签；复用既有布局、按钮和颜色，不新增独立编辑页面。先配置并预览数量，再提交；结果按需展开基础对照、父子图、掩码和深度。主平台仅保留来源选择与进入链接，避免两套表单。明确区分视觉天气、未标定光学映射、原始MP4和非物理真值增强图；未安装ControlNet时禁用并说明原因。

## 审核与评价闭环（2026-10-23）
沿用现有栏目与视觉系统。样本页保留单类框选，增加连续审核与后台LS同步状态；不强制跳出平台。批次路径展示实际计数，不将自动通过显示为人工通过。评价页分布/检测/物理三个标签，检测使用有数值标签的A/B横条及百分点差；无结果用数据缺口说明，不展示假图。

## 蜜蜡暖调重设计（2026-10-24）
视觉体系从绿灰暖纸微调为蜜蜡暖纸（canvas #f9f3e9、paper #fffdf9、sidebar #31241a、orange #d9480f、ember-gradient）。导航收敛为七项核心链路：「参考与架构」页移除（开源参考、架构图与ER图保留在 docs/ 与 docs/design/，经 README 访问）；「工程与验收」保留运行状态、Label Studio 配置、成员管理与验收标准表，交付物清单行移出平台；侧栏"查看需求规格"链接移除。新增克制微交互：主按钮渐变＋抬升辉光＋按压缩放、导航指示条与悬停位移、页面淡入切换、运行状态呼吸脉冲、阶段"执行中"高亮、HRR 曲线描画、骨架屏暖色微光、对话框缩放淡入；全部受 prefers-reduced-motion 降级。类名契约、路由、API 调用与轮询逻辑不变。

## 排版去AI味修正（2026-10-24）
用户反馈小字过多、层级不清。建立 The Type Floor Rule：禁止 <11px，固定三档字阶（14 正文 / 13 辅助 / 11.5–12.5 元信息），全站 8–11px 的历史小字统一提档；标题放大拉开对比（h1 31px、h2 19px、KPI 34px/650），中文标题字距改用 -0.01em。表格 13px、日志 12px、面包屑与成员标签提档。只改视觉值，不改任何选择器、文案与逻辑。

## 登录注册重设计与开放注册（2026-10-24）
认证弹窗重设计为分屏面板：左侧深咖啡品牌视觉（焰橙渐变标、三条价值点、工作进程/数据库状态），右侧登录/注册双标签表单。新增开放自助注册：`POST /api/register`（用户名 3–32 位字母数字下划线、密码 ≥10 位、五角色自选、默认测试师；重复返回 409），注册即加入默认项目并自动登录；`/api/setup` 保留为首次初始化通道。账户存储于 `web_user` 表（PBKDF2-SHA256 24 万次迭代加盐，不存明文），会话存 `web_session`（Cookie 12 小时），成员面板展示存储与安全说明。成员管理面板补充存储位置与安全说明。

## Skill 规范重做：去描边 + 数据唤醒（2026-10-24）
按 ai-ui-details 与 dashboard-craft 两个技能的检查单系统重做：**全站容器去 1px 描边**（表单面板、流程条、版本行、导入/审核面板、表格容器、任务详情、统计芯片），层级改由"暖纸底 #f9f3e9 ↔ 纸白 #fffdf9"色阶差＋卡片阴影表达，残留细线仅保留表格行/列表分隔与页签下划线；**输入框与次要按钮改底色提示**（surface-2 底、透明描边、聚焦焰橙描边圈）；**数据唤醒动效**：总览 KPI 五格 70ms 阶梯入场、六步流程 60ms 阶梯、样本卡 70ms 阶梯（backwards 填充不锁定 hover），KPI 数字 tabular-nums 滚动计数 900ms（reduced-motion 直出）；成功 Toast 改弹性入场（情绪动效），工具动效保持瞬时。fill 模式用 backwards，入场动画结束后不锁定 hover 位移。

## 文本可视化替换（2026-10-24）
样本页顶部两段免责长句替换为可视化：统计芯片（已保存场景/基础类型/“场景数 ≠ 独立工况覆盖”悬浮提示）、五步可视化步骤条（编号圆点＋连接线，当前步骤渐变高亮，可点击跳转）、批次审核进度改为**分段条**（已通过/已剔除/待审核三色分段＋图例芯片，自动质检通过数附“仍需人工确认”短注）。工作台“最近活动”升级为图标时间线（按事件类型映射图标：注册/完成/失败/审核/发布/任务），HRR 曲线增加渐变面积填充。不把事件流强行图表化；诚实说明以短语或悬浮提示保留，不删除。


## 编辑部级重设计·参考五标杆（2026-10-25）
应用户指定的五个审美标杆（recent.design Grok upsell、Framer、Figma、Linear、Raycast AI）做表达层升级，功能与契约零改动。视觉判断：**"编辑部级大字＋链路即主角"**——Linear 式 kicker＋大标题开场（display clamp 38–60px/750 字重/-0.03em，焰橙渐变强调短语），Raycast 式"产品自己说话"（六步链路 tile 化＋背后焰橙光带流动 chainSweep 3.4s 循环），Framer 式弹簧交互（--ease-spring 卡片悬停-5px、图标 chip 弹起），滚动进场系统（IntersectionObserver v-reveal 指令＋reveal-stagger 阶梯，reduced-motion 直出）。工作台新增 hero 区（kicker/大标题/副题/双行动按钮/径向暖光晕），通用页 h1 升至 38px、h2 21px、KPI 40px；样本卡悬停弹簧化。旧入场动画组由滚动进场系统接管。参考页已于浏览器实看提炼（Linear/Raycast/Framer 截图）。


## 暗房炽焰全站换肤（2026-10-25）
用户解放颜色与布局约束，指定五个暗色标杆（Linear/Raycast AI/Framer 等）后全站换肤：**暗房炽焰 dark ember**——近黑暖炭底（bg #0f0d0b / surface #171411 / surface-2 #1e1a16），面板靠"亮一档"分层＋黑投影，焰橙光晕（#ff6a2b，强调色只给当前态与动手处），大字编辑排版保留（h1 38 / display 60 / KPI 40）。顶栏改半透明模糊吸顶；徽章/表格/表单/空态/Toast 全部暗色化；HRR 曲线在暗底加发光；3D 场景编辑器（本就深灰）与主平台浑然一体。输入底色 #1e1a16、聚焦焰橙描边圈。验证：全站七页＋登录对话框＋移动端 400px 截图（artifacts/platform/screenshots/dark-ember/）。功能契约零改动。主题沿革：暖纸亮色（蜜蜡暖调）→ 暗房炽焰；亮色令牌留档于 git 历史。

### 内页 kicker 体系（2026-10-25 补全）
工作台之外的七个内页统一套用 kicker 页头：每页一枚英文大写胶囊（SIMULATION & SYNTHESIS / OPERATIONS / SAMPLE DATA / VERSION CONTROL / EVIDENCE LAB / ENGINEERING / 3D STUDIO）＋44px 标题＋副题，操作按钮右下对齐。工程与验收页重排：集成列表图标化（复用链路图标映射）、分组 kicker（RUNTIME / ANNOTATION / FEATURE MAP / ACCEPTANCE）。注意：对象字面量含连字符键必须加引号（'scene-editor'）。

### 主题定稿（2026-10-25）：浅色蜜蜡暖调为最终主题
暗房炽焰暗色版试运行后用户决定回归浅色。**最终主题 = 蜜蜡暖调浅色 + 本轮全部结构性升级**（编辑部级大字/kicker 页头体系/链路 tile 光带/滚动进场/弹簧交互/去描边分层/图标化集成列表）。暗色令牌已完成历史使命，如需重启暗色可参照本文件的暗色结构说明重配令牌。
