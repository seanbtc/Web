---
title: XPermission使用笔记
date: 2021-03-12 23:47:13
tags: xlib, Permission
categories: Android
---

### 一.代码位置
- [xlib-Permission](https://github.com/itemuse/XLib/blob/master/library/src/main/java/cn/xy/library/util/permissions/XPermission.java)
- [XTester-permission](https://github.com/itemuse/XTester/tree/master/permission)


### 二.引用
1. 将JitPack存储库添加到您的构建文件中
将其添加到存储库末尾的root build.gradle中：
```
allprojects {
      repositories {
      ...
      maven { url 'https://jitpack.io' }
      }
}
```

2. 添加依赖项
```
dependencies {
      ...
      implementation 'com.github.itemuse:XLib:Tag'
}
```

3. 初始化 Application中init
```
import cn.xy.library.XApp;
      ...
@Override
public void onCreate() {
      super.onCreate();
      XApp.init(this);
}
```

4. AndroidManifest.xml中添加弹出界面的activity
```
    <activity android:name="cn.xy.library.util.permissions.UtilsTransActivity"/>
```

### 三.几个常用的动态申请权限方法
   - #### 申请单个权限
AndroidManifest.xml中添加
```
    <uses-permission android:name="android.permission.RECORD_AUDIO"/>
```
java中
```
    public static String permission_RECORD_AUDIO = "android.permission.RECORD_AUDIO";
    public static String[] AidioPermissions = {
        permission_RECORD_AUDIO
    };
    ...
    /**单个权限*/
                XPermission.permission(PermissionsContract.AidioPermissions).callback(new XPermission.SimpleCallback() {
                    @Override
                    public void onGranted() {
                        XLog.i("同意");}

                    @Override
                    public void onDenied() {
                        XLog.i("拒绝");}
                }).request();
    ...            
```
申请
![](/blog/assets/2021-03-12-XPermission%E4%BD%BF%E7%94%A8%E7%AC%94%E8%AE%B0/image3.jpg)
点击同意和拒绝都会有对应的回调
   - #### 申请多个权限
AndroidManifest.xml中添加
```
    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" />
    <uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" />
```
java中
```
    public static String permission_READ_EXTERNAL_STORAGE = "android.permission.READ_EXTERNAL_STORAGE";
    public static String permission_WRITE_EXTERNAL_STORAGE = "android.permission.WRITE_EXTERNAL_STORAGE";
    public static String[] FileReadPermissions = {
            permission_READ_EXTERNAL_STORAGE
            ,permission_WRITE_EXTERNAL_STORAGE};
    ...
     /**权限组*/
                XPermission.permissionGroup(PermissionsContract.FileReadPermissions).callback(new XPermission.SimpleCallback() {
                    @Override
                    public void onGranted() {
                        XLog.i("同意");}

                    @Override
                    public void onDenied() {
                        XLog.i("拒绝");}
                }).request();        
```
申请
![](/blog/assets/2021-03-12-XPermission%E4%BD%BF%E7%94%A8%E7%AC%94%E8%AE%B0/image1.jpg)
同意后查看权限
![](/blog/assets/2021-03-12-XPermission%E4%BD%BF%E7%94%A8%E7%AC%94%E8%AE%B0/image2.jpg)
   - #### 获取所有权限
```
for (String s:XPermission.getPermissions()){
                    XLog.i(s);
                }
                break;
```
打印
```
com.xy.permission I/MainActivity.java: [ (MainActivity.java:33)#onClick ] android.permission.READ_EXTERNAL_STORAGE
com.xy.permission I/MainActivity.java: [ (MainActivity.java:33)#onClick ] android.permission.WRITE_EXTERNAL_STORAGE
com.xy.permission I/MainActivity.java: [ (MainActivity.java:33)#onClick ] android.permission.RECORD_AUDIO
```
   - #### 判断某个权限是否授予
```
XLog.i(XPermission.isGranted(PermissionsContract.AidioPermissions));
```
打印
```
com.xy.permission I/MainActivity.java: [ (MainActivity.java:55)#onClick ] true
```
用起来就是这么简单流畅，工具代码下次再补，准备睡觉。