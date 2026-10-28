# AI-07 火焰数据工作台

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

课程规定 Blender、FDS、Stable Diffusion、Label Studio、DVC、Web。现有SDD选择Vue3/TypeScript、FastAPI、PostgreSQL、Docker Compose；本次按已有设计实现，不更换算法工具。

## Users

课程项目团队：产品经理、架构师、开发工程师、测试师、运维师；执行场景生成、数据审核、版本发布和验收展示。依据用户已确认的五角色分工和SRS。

## Product Purpose

统一可视化平台贯通参数配置、物理仿真、渲染、生成增强、候选标注、人工审核、DVC发布和质量/检测效果评价。

## Operating Context

已有Python算法包、Compose引擎镜像和公开预训练权重；本地CPU/GPU工作，浏览器提交和跟踪任务。用户尚无真实标注数据，不得虚构FID、物理误差或检测提升。

## Capabilities and Constraints

实际能力与待接通能力明确区分。未审核样本不可发布；预览路线不可冒充FDS或扩散模型。保留原始SRS和已有算法。平台范围是课程实验系统，云端完整验收、独立真实数据评价需要实际运行证据。

## Evidence on Hand

artifacts/compose-verified-v3包含实际FDS/Blender/SD候选结果；artifacts/demo为程序预览，质量粗糙，仅用于流程检查。不得将这些图标成真实火灾采集图。

## Product Principles

- 每个数字有数据来源，每次执行保留参数与日志。
- 核心流程可操作，缺失配置明确说明如何补齐。
- 页面显示业务状态，不展示伪造成功。
- 成本只记录资源用量与公式，不填写金额。
