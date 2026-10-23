# TLS 证书

完整 Nginx 说明见[部署指南](../../../../docs/getting-started/deployment.md#nginx)。

安装器可帮助准备 Nginx 证书：

- 检查 `WEBHOOK_HOST` 和 `MINIAPP_HOST` 的 DNS A 记录；
- 通过 Certbot Cloudflare DNS-01 签发通配符证书；
- 通过 Certbot 独立 HTTP-01 签发各域名证书；
- 使用本目录已准备的文件。

手动准备时，证书放入与 `WEBHOOK_HOST` 和 `MINIAPP_HOST` 对应的子目录：

```text
ssl/
  webhooks.example.com/
    fullchain.pem
    privkey.pem
  app.example.com/
    fullchain.pem
    privkey.pem
```
