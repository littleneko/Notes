官方固件下载：https://downloads.openwrt.org/releases/21.02.6/targets/x86/64/

OpenWrt x86：https://openwrt.org/docs/guide-user/installation/openwrt_x86

# OpenWrt x86 官方 squashfs 固件安装时扩容方法

## 扩容

OpenWrt 固件的 squashfs 分区会在首次启动时自动扩展到所分配的全部空间，所以我们只需要使用 fdisk 简单地更改 squashfs 分区的大小，然后重启开始自动安装即可，不需要重新编译或使用固件生成器重新生成。

注意：此方法仅适合刚把镜像写入磁盘还未启动以及还未将镜像写入磁盘这两种情况，一旦系统启动，squashfs 分区大小就已经确定了，如果要更改只能使用losetup 挂载并执行 resize.f2fs 扩展大小。

**详细步骤如下**：

1. 如果要修改的是 IMG 文件，需要先扩展文件的大小，如果 IMG 已经写入了磁盘则直接从第 2 步开始

   ```shell
   > qemu-img resize openwrt-21.02.6-x86-64-generic-squashfs-combined-efi.img 1040M
   ```

2. 使用 fdisk 重新分区：如果 IMG 已经写入了磁盘则将文件路径改为磁盘路径即可，例如 `sudo fdisk /dev/sda`

   ```shell
   > fdisk openwrt-21.02.6-x86-64-generic-squashfs-combined-efi.img
   
   Welcome to fdisk (util-linux 2.38.1).
   Changes will remain in memory only, until you decide to write them.
   Be careful before using the write command.
   
   GPT PMBR size mismatch (246846 != 2129919) will be corrected by write.
   The backup GPT table is corrupt, but the primary appears OK, so that will be used.
   The backup GPT table is not on the end of the device. This problem will be corrected by write.
   
   Command (m for help): 
   ```

3. 输入 `p` 查看当前分区表

   ```
   Command (m for help): p
   
   Disk openwrt-21.02.6-x86-64-generic-squashfs-combined-efi.img: 1.02 GiB, 1090519040 bytes, 2129920 sectors
   Units: sectors of 1 * 512 = 512 bytes
   Sector size (logical/physical): 512 bytes / 512 bytes
   I/O size (minimum/optimal): 512 bytes / 512 bytes
   Disklabel type: gpt
   Disk identifier: 1DEA8BE8-276D-0BB7-73FC-EFDD241C0300
   
   Device                                                      Start    End Sectors  Size Type
   openwrt-21.02.6-x86-64-generic-squashfs-combined-efi.img1     512  33279   32768   16M EFI System
   openwrt-21.02.6-x86-64-generic-squashfs-combined-efi.img2   33792 246783  212992  104M Microsoft basic data
   openwrt-21.02.6-x86-64-generic-squashfs-combined-efi.img128    34    511     478  239K BIOS boot
   
   Partition table entries are not in disk order.
   
   Command (m for help): 
   ```

4. 记下第 2 个分区的起始位置 `33792`

5. 删除第 2 个分区

   ```
   Command (m for help): d
   Partition number (1,2,128, default 128): 2
   
   Partition 2 has been deleted.
   
   Command (m for help): 
   ```

6. 新建分区

   1. First sector 输入刚刚记下的第 2 个分区的起始位置 `33792`
   2. Last sector 输入新分区的大小并按回车，例如 +1G 为分配 1G 大小的分区，注意分配的大小不可超过上面所扩展的大小或磁盘大小，如果要使用所有未使用的空间直接留空按回车即可
   3. 不 remove signature

   ```
   Command (m for help): n
   Partition number (2-127, default 2): 
   First sector (33280-2129886, default 34816): 33792
   Last sector, +/-sectors or +/-size{K,M,G,T,P} (33792-2129886, default 2127871): 
   
   Created a new partition 2 of type 'Linux filesystem' and of size 1022.5 MiB.
   Partition #2 contains a squashfs signature.
   
   Do you want to remove the signature? [Y]es/[N]o: N
   
   Command (m for help): 
   ```

7. 再次输入 `p` 确认分区是否正确，如果不正确输入 `q` 退出重新开始分区

   ```
   Command (m for help): p
   
   Disk openwrt-21.02.6-x86-64-generic-squashfs-combined-efi.img: 1.02 GiB, 1090519040 bytes, 2129920 sectors
   Units: sectors of 1 * 512 = 512 bytes
   Sector size (logical/physical): 512 bytes / 512 bytes
   I/O size (minimum/optimal): 512 bytes / 512 bytes
   Disklabel type: gpt
   Disk identifier: 1DEA8BE8-276D-0BB7-73FC-EFDD241C0300
   
   Device                                                      Start     End Sectors    Size Type
   openwrt-21.02.6-x86-64-generic-squashfs-combined-efi.img1     512   33279   32768     16M EFI System
   openwrt-21.02.6-x86-64-generic-squashfs-combined-efi.img2   33792 2127871 2094080 1022.5M Linux filesystem
   openwrt-21.02.6-x86-64-generic-squashfs-combined-efi.img128    34     511     478    239K BIOS boot
   
   Partition table entries are not in disk order.
   
   Command (m for help): 
   ```

8. 输入 `w` 并按回车保存更改

   ```
   Command (m for help): w
   The partition table has been altered.
   Syncing disks.
   ```

修改完成后将 IMG 文件直接写入磁盘并重启即可，如果 IMG 已经写入了磁盘则直接重启系统开始自动安装

## 修改 grub.cfg

上面重新分区导致 dev/sda2 的 UUID 改变了，而 grub 是使用 UUID 标识的 root，所以需要修改 grub.cfg 才能启动。

在上面 fdisk 分区完成后，我们需要记录下 UUID "717A7C6F-4493-544A-B7C9-FA614F06C968" 和 第一个分区（boot 分区）的 Start 512。

```shel
Command (m for help): i
Partition number (1,2,128, default 128): 2

         Device: openwrt-21.02.6-x86-64-generic-squashfs-combined-efi.img2
          Start: 33792
            End: 2127871
        Sectors: 2094080
           Size: 1022.5M
           Type: Linux filesystem
      Type-UUID: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
           UUID: 717A7C6F-4493-544A-B7C9-FA614F06C968

Command (m for help): p
Disk openwrt-21.02.6-x86-64-generic-squashfs-combined-efi.img: 1.02 GiB, 1090519040 bytes, 2129920 sectors
Units: sectors of 1 * 512 = 512 bytes
Sector size (logical/physical): 512 bytes / 512 bytes
I/O size (minimum/optimal): 512 bytes / 512 bytes
Disklabel type: gpt
Disk identifier: 1DEA8BE8-276D-0BB7-73FC-EFDD241C0300

Device                                                      Start     End Sectors    Size Type
openwrt-21.02.6-x86-64-generic-squashfs-combined-efi.img1     512   33279   32768     16M EFI System
openwrt-21.02.6-x86-64-generic-squashfs-combined-efi.img2   33792 2127871 2094080 1022.5M Linux filesystem
openwrt-21.02.6-x86-64-generic-squashfs-combined-efi.img128    34     511     478    239K BIOS boot

Partition table entries are not in disk order.

Command (m for help): 
```

然后退出 fdisk，挂载 img 文件的第 1 个分区

```
sudo mount -o loop,offset=262144 openwrt-21.02.6-x86-64-generic-squashfs-combined-efi.img ./mnt
```


其中 offset 的计算方式是 Start * 512 （Sector size (logical/physical): 512 bytes / 512 bytes）

在挂载的目录下修改 grub.cfg 文件，把 root 的 UUID 改成新的 UUID，修改完直接 `sudo umount ./mnt` 就保存了。

![image-20230415220406163](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20230415220406163.png)

# img 转换

```
qemu-img convert -f raw -O vmdk openwrt-21.02.1-x86-64-generic-squashfs-combined-efi.img openwrt-21.02.1-x86-64-generic-squashfs-combined-efi.vmdk

vmkfstools -i ../Data/openwrt-21.02.1-x86-64-generic-squashfs-combined-efi.vmdk OpenWrt\ Gateway.vmdk 
```

# 常用的软件安装

```
luci-app-ttyd
luci-app-ttyd-zh-cn
block-mount
luci-compat
luci-app-ddns
luci-app-ddns-zh-cn
ddns-scripts
ddns-scripts-cloudflare
luci-app-wol
luci-i18n-wol-zh-cn
luci-app-frpc
luci-i18n-frpc-zh-cn
luci-app-upnp
luci-i18n-upnp-zh-cn
luci-app-nlbwmon
luci-i18n-nlbwmon-zh-cn
luci-app-samba4
luci-i18n-samba4-zh-cn

opkg install luci-app-ttyd luci-i18n-ttyd-zh-cn block-mount luci-compat luci-app-ddns luci-i18n-ddns-zh-cn ddns-scripts ddns-scripts-cloudflare luci-app-wol luci-i18n-wol-zh-cn luci-app-frpc luci-i18n-frpc-zh-cn luci-app-upnp luci-i18n-upnp-zh-cn luci-app-nlbwmon luci-i18n-nlbwmon-zh-cn luci-app-samba4 luci-i18n-samba4-zh-cn


luci-app-filetransfer
luci-app-webadmin
luci-app-vlmcsd
luci-app-vsftpd
luci-app-ipsec-vpnd
luci-app-zerotier
luci-app-arpbind
luci-app-flowoffload
```

