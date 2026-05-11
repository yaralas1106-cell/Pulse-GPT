# TOMI_MCP Remote Script 安装说明

## 1. 复制文件夹

把 `TOMI_MCP/` 整个文件夹复制到 Ableton 的 User Remote Scripts 目录：

**Windows：**
```
C:\Users\<你的用户名>\Documents\Ableton\User Library\Remote Scripts\
```

复制后结构应该是：
```
Remote Scripts\
  └── TOMI_MCP\
        └── __init__.py
```

## 2. 在 Ableton 中激活

1. 启动 Ableton Live
2. 打开 **Preferences → Link / Tempo / MIDI**
3. 在任意一行 **Control Surface** 下拉框中选择 **TOMI_MCP**
4. Input / Output 保持 None 即可

## 3. 验证连接

激活后 Remote Script 会在 **9877 端口**开启 socket 服务。

用浏览器访问：
```
http://localhost:8002/health
```

返回 `"ableton_connected": true` 说明连接成功。

## 注意事项

- 每次重启 Ableton 都需要 Script 处于激活状态
- 如果 9877 端口被占用，修改 `__init__.py` 顶部的 `PORT = 9877`
- Ableton Log 文件路径（查看错误）：
  `C:\Users\<用户名>\AppData\Roaming\Ableton\Live x.x.x\Preferences\Log.txt`
