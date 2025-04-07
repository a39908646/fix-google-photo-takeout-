一个用来修复谷歌相册导出文件丢失时间线的python脚本
·依赖：
  1.exiftool
  安装最新版exiftool并配置好环境变量
  2.python依赖
  参考脚本
·使用：
以管理员权限定位到要执行的目录：python fixmetadata.py -d "/path/dir"
支持自动递归子文件夹
执行后会生成透明操作日志及错误日志
