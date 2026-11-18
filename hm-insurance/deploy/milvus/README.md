# Milvus 配置

`deploy/docker-compose.yml` 会把本目录的 `user.yaml` 以只读方式挂载到
Milvus 容器的 `/milvus/configs/user.yaml`。

`user.yaml` 里是真实密钥，已被根目录 `.gitignore` 忽略，不纳入版本库。
首次部署先复制示例，再填入自己的 Key：

```bash
cp deploy/milvus/user.example.yaml deploy/milvus/user.yaml
```

需要填写的是 `credential.dashscope_apikey.apikey`。
