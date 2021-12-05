# centos 6 使用libcgconfig
## 相关概念

- subsystem: 可以控制的资源, 比如cpu,mem
- hierarchy
- control groups

![](https://access.redhat.com/webassets/avalon/d/Red_Hat_Enterprise_Linux-6-Resource_Management_Guide-en-US/images/fe94409bf79906ecb380e8fbd8063016/RMG-rule1.png#alt=Rule%201)

ref: [https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/6/html/resource_management_guide/sec-relationships_between_subsystems_hierarchies_control_groups_and_tasks](https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/6/html/resource_management_guide/sec-relationships_between_subsystems_hierarchies_control_groups_and_tasks)

## 相关命令
```bash
# 安装cgroup
> yum install libcgroup libcgroup-tools
 
# 启动cgroup
> #systemctl start cgconfig
> service cgconfig start
 
# 配置开机启动
> #systemctl enable cgconfig
 
# 查看cgroup mount信息
> mount -t cgroup
cgroup on /sys/fs/cgroup/systemd type cgroup (rw,nosuid,nodev,noexec,relatime,xattr,release_agent=/usr/lib/systemd/systemd-cgroups-agent,name=systemd)
cgroup on /sys/fs/cgroup/blkio type cgroup (rw,nosuid,nodev,noexec,relatime,blkio)
cgroup on /sys/fs/cgroup/freezer type cgroup (rw,nosuid,nodev,noexec,relatime,freezer)
cgroup on /sys/fs/cgroup/devices type cgroup (rw,nosuid,nodev,noexec,relatime,devices)
cgroup on /sys/fs/cgroup/cpu,cpuacct type cgroup (rw,nosuid,nodev,noexec,relatime,cpuacct,cpu)
cgroup on /sys/fs/cgroup/memory type cgroup (rw,nosuid,nodev,noexec,relatime,memory)
cgroup on /sys/fs/cgroup/perf_event type cgroup (rw,nosuid,nodev,noexec,relatime,perf_event)
cgroup on /sys/fs/cgroup/net_cls,net_prio type cgroup (rw,nosuid,nodev,noexec,relatime,net_prio,net_cls)
cgroup on /sys/fs/cgroup/pids type cgroup (rw,nosuid,nodev,noexec,relatime,pids)
cgroup on /sys/fs/cgroup/cpuset type cgroup (rw,nosuid,nodev,noexec,relatime,cpuset)
cgroup on /sys/fs/cgroup/hugetlb type cgroup (rw,nosuid,nodev,noexec,relatime,hugetlb)
 
# 查看subsystem信息
# 其中 cpu memory 等都是一个subsystem
# subsystem后面的目录表示该subsystem附加到的HIERARCHY, 比如cpu附加到/sys/fs/cgroup/cpu这个HIERARCHY中
> lssubsys -am
cpuset /sys/fs/cgroup/cpuset
cpu,cpuacct /sys/fs/cgroup/cpu,cpuacct
memory /sys/fs/cgroup/memory
devices /sys/fs/cgroup/devices
freezer /sys/fs/cgroup/freezer
net_cls,net_prio /sys/fs/cgroup/net_cls,net_prio
blkio /sys/fs/cgroup/blkio
perf_event /sys/fs/cgroup/perf_event
hugetlb /sys/fs/cgroup/hugetlb
pids /sys/fs/cgroup/pids
 
# 创建HIERARCHY 
# 注意，centos 7安装好cgroup后，就已经预设了一些HIERARCHY(上面mount -t cgroup看到的)
# 因为一个subsystem只能mount到一个HIERARCHY上，所以不能再mount了，除非先umount
> mkdir /cgroup/test_group
> mount -t cgroup -o cpu, memory test_group /cgroup/test_group

# 删除HIERARCHY
> umount /cgroup/test_group
 
# 创建临时cgroup组
# 创建完成后会发现在 /sys/fs/cgroup/cpu, /sys/fs/cgroup/memory, /sys/fs/cgroup/blkio 下分别多了 manager_group 目录
> cgcreate -g cpu,memory,blkio:/manager_group
 
# 删除cgroup组
> cgdelete -g cpu,memory,blkio:/manager_group
 
# 设置cgroup组参数
# 注意：这里的设备号应该是整块磁盘的，而不是分区的
> cgset -r cpu.shares=4096 manager_group
> cgset -r cpu.cfs_period_us=100000 manager_group
> cgset -r cpu.cfs_quota_us=20000 manager_group
> cgset -r blkio.throttle.read_iops_device="253:0 2150" manager_group
> cgset -r blkio.throttle.write_iops_device="253:0 1170" manager_group
> cgset -r blkio.throttle.read_bps_device="253:0 104857619" manager_group
> cgset -r blkio.throttle.write_bps_device="253:0 52428819" manager_group
 
# 或者直接改写fs上的值
> echo "8:0 10485760" > /sys/fs/cgroup/blkio/manager_group/blkio.throttle.read_bps_device
 
# 在cgroup中启动进程
> cgexec --sticky -g cpu,memory,blkio:manager_group firefox http://www.redhat.com
 
# 附加一个进程到cgroup中
> cgclassify -g cpu,memory,blkio:manager_group 1701
```
## 配置文件示例
```
# file: /etc/cgconfig.conf
# mount位置，默认不写就在/sys/fs/cgroup下面
mount {
  cpuset  = /cgroup/cpuset;
  cpu  = /cgroup/cpu;
  cpuacct  = /cgroup/cpuacct;
  memory  = /cgroup/memory;
  devices  = /cgroup/devices;
  freezer  = /cgroup/freezer;
  net_cls  = /cgroup/net_cls;
  blkio  = /cgroup/blkio;
}

# file: /etc/cgconfig.d/manager_group.conf
# 创建一个新的cgroup
group manager_group {
    cpu {
        cpu.shares=4096;
        cpu.cfs_period_us=100000;
        cpu.cfs_quota_us=20000;
    }
    memory {
        memory.limit_in_bytes=2147483648;
    }
    blkio {
        blkio.throttle.read_iops_device="253:0 1000";
        blkio.throttle.write_iops_device="253:0 1000";
        blkio.throttle.read_bps_device="253:0 26214400";
        blkio.throttle.write_bps_device="253:0 26214400";
    }
}
```
修改配置文件后执行 service cgconfig restart 即可生效

1. 在centos 7上，需要先 systemctl stop cgconfig，然后执行 cgclear 清理所有默认挂载点后，才能配置mount位置。
2. 在centos 7上发现重启机器又会默认挂载到/sys/fs/cgroup下，导致 systemctl start cgconfig 不成功，目前还没发现方法可以不默认挂载
# centos 7 使用systemd
默认情况下，**systemd** 会自动创建 _slice_、_scope_ 和 _service_ 单位的层级，来为 cgroup 树提供统一结构。使用 `systemctl` 指令，您可以通过创建自定义 slice 进一步修改此结构，详情请参阅〈[第 2.1 节 “创建控制群组”](https://access.redhat.com/documentation/zh-cn/red_hat_enterprise_linux/7/html/resource_management_guide/chap-Using_Control_Groups#sec-Creating_Cgroups)〉。**systemd** 也自动为 `/sys/fs/cgroup/` 目录中重要的 kernel 资源管控器（参见〈[Red Hat Enterprise Linux 7 中可用的管控器](https://access.redhat.com/documentation/zh-cn/red_hat_enterprise_linux/7/html/resource_management_guide/br-Resource_Controllers_in_Linux_Kernel#itemlist-Available_Controllers_in_Red_Hat_Enterprise_Linux_7)〉）挂载层级。

在centos7上，虽然也可以使用上面的方法配置cgroup，但是官方不建议这么做，官方建议的方法是使用systemd管理。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1564035718478-33101398-6ec9-4f81-9324-054959921dfd.png" alt="img" style="zoom:50%;" />

使用systemd管理cgroup不需要安装libcgconfig和libcgconfig-tools包。

## 相关概念
### systemd 的单位类型

系统中运行的所有进程，都是 **systemd** init 进程的子进程。在资源管控方面，systemd 提供了三种单位类型（如需 `systemd` 单位类型完整列表，请参阅《[Red Hat Enterprise Linux 7 系统管理员指南](https://access.redhat.com/site/documentation/en-US/Red_Hat_Enterprise_Linux/7-Beta/html/System_Administrators_Guide) · _使用 systemd 管理 service_》）：

- **service **—— 一个或一组进程，由 `systemd` 依据单位配置文件启动。service 对指定进程进行封装，这样进程可以作为一个整体被启动或终止。service 参照以下方式命名：_name_```
service
```

其中，_name_ 代表服务名称。
- **scope** —— 一组外部创建的进程。由强制进程通过 `fork()` 函数启动和终止、之后被 **systemd** 在运行时注册的进程，scope 会将其封装。例如：用户会话、 容器和虚拟机被认为是 scope。scope 的命名方式如下：_name_```
scope
```

其中，_name_ 代表 scope 名称。
- **slice** —— 一组按层级排列的单位。slice 并不包含进程，但会组建一个层级，并将 scope 和 service 都放置其中。真正的进程包含在 scope 或 service 中。在这一被划分层级的树中，每一个 slice 单位的名字对应通向层级中一个位置的路径。小横线（"`-`"）起分离路径组件的作用。例如，如果一个 slice 的名字是：_parentname_```
slice
```

这说明 _parent_-_name_.`slice` 是 _parent_.`slice` 的一个子 slice。这一子 slice 可以再拥有自己的子 slice，被命名为：_parent_-_name_-_name2_.`slice`，以此类推。
根 slice 的表示方式：```
-.slice
```



service、scope 和 slice 单位直接映射到 cgroup 树中的对象。当这些单位被激活，它们会直接一一映射到由单位名建立的 cgroup 路径中。例如，_ex.service_ 属于 _test-waldo.slice_，会直接映射到 cgroup `test.slice/test-waldo.slice/ex.service/` 中。
**因此我们只需要新建一个slice，然后把要执行的进程放到该slice里即可**。
## 配置slice
### 新建slice
slice配置文件位置: /usr/lib/systemd/system/xxx.slice
文件参考默认的user.slice就行

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1564035718513-c9227805-8dca-4572-8e39-be0020c935eb.png)

### 添加一个service到slice
在service的配置文件中加上 _**Slice=group-name.slice**_
## 相关命令
### 设置slice参数
```
systemctl set-property test.slice CPUQuota=20%
```
所有可设置参数查看
```
man systemd.resource-control
```
**设置的参数保存在 /etc/systemd/system/test.slice.d/ 下**
### 临时在slice下启动进程
```
systemd-run --unit=cpu_100 --scope --slice=test /root/cpu_100
```
要停止该进程只需要执行 systemctl stop cpu_100 即可
### 其他

- 查看cgroup: systemd-cgtop

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1564035718550-9b380c46-b7b2-4843-a3f9-8307e7e2d7ca.png)

- 查看cgroup树: systemd-cgls

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1564035718582-059427ce-8bf5-4b14-8080-931cd31e8b0d.png)

# Reference

1. [https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/6/html/resource_management_guide/index](https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/6/html/resource_management_guide/index)
2. [https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/7/html/resource_management_guide/index](https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/7/html/resource_management_guide/index)
3. [https://coolshell.cn/articles/17049.html](https://coolshell.cn/articles/17049.html)

## Attachments:
![](https://cdn.nlark.com/yuque/0/2019/gif/385742/1564035719116-7d1d28d6-9b56-49d1-a74f-c90d954c2275.gif#alt=&height=8&width=8)[image2019-5-3_1-21-39.png](https://cdn.nlark.com/yuque/0/2019/png/385742/1564035718478-33101398-6ec9-4f81-9324-054959921dfd.png)
![](https://cdn.nlark.com/yuque/0/2019/gif/385742/1564035719116-7d1d28d6-9b56-49d1-a74f-c90d954c2275.gif#alt=&height=8&width=8)[image2019-5-3_1-22-0.png](https://cdn.nlark.com/yuque/0/2019/png/385742/1564035718513-c9227805-8dca-4572-8e39-be0020c935eb.png)
![](https://cdn.nlark.com/yuque/0/2019/gif/385742/1564035719116-7d1d28d6-9b56-49d1-a74f-c90d954c2275.gif#alt=&height=8&width=8)[image2019-5-3_1-22-17.png](https://cdn.nlark.com/yuque/0/2019/png/385742/1564035718550-9b380c46-b7b2-4843-a3f9-8307e7e2d7ca.png)
![](https://cdn.nlark.com/yuque/0/2019/gif/385742/1564035719116-7d1d28d6-9b56-49d1-a74f-c90d954c2275.gif#alt=&height=8&width=8)[image2019-5-3_1-22-30.png](https://cdn.nlark.com/yuque/0/2019/png/385742/1564035718582-059427ce-8bf5-4b14-8080-931cd31e8b0d.png)