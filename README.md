# 3C数码热点中心

本地运营工作台原型，覆盖3C数码新品、技术趋势、品牌事件、消费争议、用户观点和破圈复盘。

## 启动

```powershell
python server.py
```

默认访问：`http://localhost:8788`

## 云部署

服务支持通过环境变量配置监听地址和端口：

```powershell
$env:HOST = "0.0.0.0"
$env:PORT = "8788"
$env:REFRESH_SECONDS = "3600"
python server.py
```

- `HOST`：监听地址，云部署时使用 `0.0.0.0`
- `PORT`：平台分配端口，未设置时默认 `8788`
- `REFRESH_SECONDS`：后台抓取刷新周期，默认 `3600` 秒

### JoyCode / 京东云快速部署

当前目录已经补齐最小容器入口，可直接作为本地项目部署：

- 入口文件：`server.py`
- 页面文件：`index.html`
- 容器文件：`Dockerfile`
- 健康检查：`/healthz`

推荐部署方式：
1. 在 JoyCode 中创建本地项目并导入当前目录
2. 点击“快速部署”
3. 如需自定义环境变量，配置：
   - `HOST=0.0.0.0`
   - `PORT=8788`（若平台自动注入端口，则以平台值为准）
   - `REFRESH_SECONDS=3600`
4. 部署成功后，通过返回的公网链接访问页面

接口：
- `/api/hotspots`：返回最近一次成功抓取的热点快照
- `/healthz`：健康检查

已接入真实采集服务：百度、今日头条、抖音、微博、快手、小红书公开入口，以及 IT之家、雷科技、少数派 RSS。热点数据由后台按小时刷新；受限平台会返回状态，不绕过登录、验证码或访问控制。

## GitHub Pages 自动更新

`.github/workflows/update-hotspots.yml` 每小时运行一次 `build-static-data.py`，将最新快照写入根目录 `hotspots.json` 并提交回 `main`。页面打开后也会每小时重新拉取一次快照，并通过时间戳参数避开 CDN 缓存。

为防止临时网络故障覆盖正常数据，采集结果少于 20 条或没有成功来源时任务会失败并保留上一版快照。也可以在 GitHub Actions 页面手动运行 `Update hotspot data`。
