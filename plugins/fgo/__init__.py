try:
    import nonebot
    # 能拿到 driver 说明 nonebot.init() 已执行
    nonebot.get_driver()
except Exception:
    # 离线导入（测试/脚本）不加载命令
    pass
else:
    from . import commands  # noqa: F401