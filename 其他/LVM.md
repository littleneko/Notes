1. gparted iso 扩展分区

2. PV/VG/LV 扩容

   1. pvdisplay
   2. vgdisplay
   3. lvdisplay

   `sudo lvextend -l +100%FREE /dev/ubuntu-vg/lv-0`

3. 文件系统扩容

  `sudo resize2fs /dev/ubuntu-vg/lv-0`