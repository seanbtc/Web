---
title: PackageManager基础
date: 2021-03-25 19:30:51
tags: xlib, PackageManager, ActivityManger
categories: Android
---

### 一.代码位置
   - [xlib-Application](https://github.com/itemuse/XLib/blob/master/library/src/main/java/cn/xy/library/util/app/XApplication.java)
   - [XTester-packagemanger](https://github.com/itemuse/XTester/tree/master/packagemanger)

### 二.引用方式
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

4. AndroidManifest.xml中添加UID
```
    android:sharedUserId="android.uid.system"
```

### 三.demo
![](/blog/assets/2021-03-25-PackageManager%E5%9F%BA%E7%A1%80/list.gif)

### 四.PackageManager几个方法
   - #### 判断APP是否安装
```
    /**
     * Return whether the app is installed.
     *
     * @param pkgName The name of the package.
     * @return {@code true}: yes<br>{@code false}: no
     */
    public static boolean isAppInstalled(@NonNull final String pkgName) {
        PackageManager packageManager = XApp.getApp().getPackageManager();
        try {
            return packageManager.getApplicationInfo(pkgName, 0) != null;
        } catch (PackageManager.NameNotFoundException e) {
            e.printStackTrace();
            return false;
        }
    }
```

   - #### 判断APP是否DEBUG版本
```
   /**
     * Return whether it is a debug application.
     *
     * @param packageName The name of the package.
     * @return {@code true}: yes<br>{@code false}: no
     */
    public static boolean isAppDebug(final String packageName) {
        if (isSpace(packageName)) return false;
        try {
            PackageManager pm = XApp.getApp().getPackageManager();
            ApplicationInfo ai = pm.getApplicationInfo(packageName, 0);
            return ai != null && (ai.flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0;
        } catch (PackageManager.NameNotFoundException e) {
            e.printStackTrace();
            return false;
        }
    }
```

   - #### 判断APP是否系统应用
```
    /**
     * Return whether it is a system application.
     *
     * @param packageName The name of the package.
     * @return {@code true}: yes<br>{@code false}: no
     */
    public static boolean isAppSystem(final String packageName) {
        if (isSpace(packageName)) return false;
        try {
            PackageManager pm = XApp.getApp().getPackageManager();
            ApplicationInfo ai = pm.getApplicationInfo(packageName, 0);
            return ai != null && (ai.flags & ApplicationInfo.FLAG_SYSTEM) != 0;
        } catch (PackageManager.NameNotFoundException e) {
            e.printStackTrace();
            return false;
        }
    }
```

   - #### 判断APP是否正在运行
```
    /**
     * Return whether application is running.
     *
     * @param pkgName The name of the package.
     * @return {@code true}: yes<br>{@code false}: no
     */
    public static boolean isAppRunning(@NonNull final String pkgName) {
        int uid;
        PackageManager packageManager = XApp.getApp().getPackageManager();
        try {
            ApplicationInfo ai = packageManager.getApplicationInfo(pkgName, 0);
            if (ai == null) return false;
            uid = ai.uid;
        } catch (PackageManager.NameNotFoundException e) {
            e.printStackTrace();
            return false;
        }
        ActivityManager am = (ActivityManager) XApp.getApp().getSystemService(Context.ACTIVITY_SERVICE);
        if (am != null) {
            List<ActivityManager.RunningTaskInfo> taskInfo = am.getRunningTasks(Integer.MAX_VALUE);
            if (taskInfo != null && taskInfo.size() > 0) {
                for (ActivityManager.RunningTaskInfo aInfo : taskInfo) {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                        if (pkgName.equals(aInfo.baseActivity.getPackageName())) {
                            return true;
                        }
                    }
                }
            }
            List<ActivityManager.RunningServiceInfo> serviceInfo = am.getRunningServices(Integer.MAX_VALUE);
            if (serviceInfo != null && serviceInfo.size() > 0) {
                for (ActivityManager.RunningServiceInfo aInfo : serviceInfo) {
                    if (uid == aInfo.uid) {
                        return true;
                    }
                }
            }
        }
        return false;
    }
```

   - #### 获取APP图标
```
    /**
     * Return the application's icon.
     *
     * @param packageName The name of the package.
     * @return the application's icon
     */
    public static Drawable getAppIcon(final String packageName) {
        if (isSpace(packageName)) return null;
        try {
            PackageManager pm = XApp.getApp().getPackageManager();
            PackageInfo pi = pm.getPackageInfo(packageName, 0);
            return pi == null ? null : pi.applicationInfo.loadIcon(pm);
        } catch (PackageManager.NameNotFoundException e) {
            e.printStackTrace();
            return null;
        }
    }
```

   - #### 获取APP名
```
    /**
     * Return the application's name.
     *
     * @param packageName The name of the package.
     * @return the application's name
     */
    public static String getAppName(final String packageName) {
        if (isSpace(packageName)) return "";
        try {
            PackageManager pm = XApp.getApp().getPackageManager();
            PackageInfo pi = pm.getPackageInfo(packageName, 0);
            return pi == null ? null : pi.applicationInfo.loadLabel(pm).toString();
        } catch (PackageManager.NameNotFoundException e) {
            e.printStackTrace();
            return "";
        }
    }
```

   - #### 获取APP路径
```
    /**
     * Return the application's path.
     *
     * @param packageName The name of the package.
     * @return the application's path
     */
    public static String getAppPath(final String packageName) {
        if (isSpace(packageName)) return "";
        try {
            PackageManager pm = XApp.getApp().getPackageManager();
            PackageInfo pi = pm.getPackageInfo(packageName, 0);
            return pi == null ? null : pi.applicationInfo.sourceDir;
        } catch (PackageManager.NameNotFoundException e) {
            e.printStackTrace();
            return "";
        }
    }
```

   - #### 获取APP版名
```
    /**
     * Return the application's version name.
     *
     * @param packageName The name of the package.
     * @return the application's version name
     */
    public static String getAppVersionName(final String packageName) {
        if (isSpace(packageName)) return "";
        try {
            PackageManager pm = XApp.getApp().getPackageManager();
            PackageInfo pi = pm.getPackageInfo(packageName, 0);
            return pi == null ? null : pi.versionName;
        } catch (PackageManager.NameNotFoundException e) {
            e.printStackTrace();
            return "";
        }
    }
```

   - #### 获取APP版本号
```
    /**
     * Return the application's version code.
     *
     * @param packageName The name of the package.
     * @return the application's version code
     */
    public static int getAppVersionCode(final String packageName) {
        if (isSpace(packageName)) return -1;
        try {
            PackageManager pm = XApp.getApp().getPackageManager();
            PackageInfo pi = pm.getPackageInfo(packageName, 0);
            return pi == null ? -1 : pi.versionCode;
        } catch (PackageManager.NameNotFoundException e) {
            e.printStackTrace();
            return -1;
        }
    }
```

   - #### 获取APP签名
```
    /**
     * Return the application's signature.
     *
     * @param packageName The name of the package.
     * @return the application's signature
     */
    public static Signature[] getAppSignature(final String packageName) {
        if (isSpace(packageName)) return null;
        try {
            PackageManager pm = XApp.getApp().getPackageManager();
            @SuppressLint("PackageManagerGetSignatures")
            PackageInfo pi = pm.getPackageInfo(packageName, PackageManager.GET_SIGNATURES);
            return pi == null ? null : pi.signatures;
        } catch (PackageManager.NameNotFoundException e) {
            e.printStackTrace();
            return null;
        }
    }
```

   - #### 获取APP的UI-ID
```
    /**
     * Return the application's user-ID.
     *
     * @param pkgName The name of the package.
     * @return the application's signature for MD5 value
     */
    public static int getAppUid(String pkgName) {
        try {
            ApplicationInfo ai = XApp.getApp().getPackageManager().getApplicationInfo(pkgName, 0);
            if (ai != null) {
                return ai.uid;
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
        return -1;
    }
```

   - #### 获取APP信息
```
    /**
     * Return the application's information.
     * <ul>
     * <li>name of package</li>
     * <li>icon</li>
     * <li>name</li>
     * <li>path of package</li>
     * <li>version name</li>
     * <li>version code</li>
     * <li>is system</li>
     * </ul>
     *
     * @param packageName The name of the package.
     * @return the application's information
     */
    public static AppInfo getAppInfo(final String packageName) {
        try {
            PackageManager pm = XApp.getApp().getPackageManager();
            if (pm == null) return null;
            return getBean(pm, pm.getPackageInfo(packageName, 0));
        } catch (PackageManager.NameNotFoundException e) {
            e.printStackTrace();
            return null;
        }
    }
```
   - #### 获取/设置APP启用/禁用状态
    - 设置
    ```
    /**
     * @param packageName to hidden or show app
     * @param enable true ENABLED ; false DISABLED
     * need android:sharedUserId="android.uid.system"
     */
    public void changeAppState(String packageName, boolean enable){
        try {
            PackageManager packageManager = XApp.getApp().getPackageManager();
            if(enable){
                packageManager.setApplicationEnabledSetting(packageName,PackageManager.COMPONENT_ENABLED_STATE_ENABLED,0);
            }else{
                packageManager.setApplicationEnabledSetting(packageName,PackageManager.COMPONENT_ENABLED_STATE_DISABLED,0);
            }
        } catch (Exception e) {
            XLog.debug(e.getMessage());
        }
    }
    ```
    - 获取
   ```
       /**
     * @return
     * -1 no intalled
     *  1 ENABLED
     *  2 DISABLED
     *
     */
    public int getAppState(String packageName) {
        try {
            PackageManager packageManager = XApp.getApp().getPackageManager();
            return packageManager.getApplicationEnabledSetting(packageName);
        } catch (Exception e) {
            XLog.debug(e.getMessage());
            return -1;
        }
    }
   ```

   - #### 获取/设置Activity启用/禁用状态
    - 获取
    ```
    /**
     * @return
     * -1 no intalled
     *  1 ENABLED
     *  2 DISABLED
     */
    public int getActivityState(ComponentName componentName){
        try {
            PackageManager packageManager = XApp.getApp().getPackageManager();
            return packageManager.getComponentEnabledSetting(componentName);
        } catch (Exception e){
            return -1;
        }
    }
    ```
    - 设置
    ```
    /**
     * @param componentName to hidden or show activity
     * @param enable true ENABLED ; false DISABLED
     * need android:sharedUserId="android.uid.system"
     */
    public void changActivityState(ComponentName componentName,boolean enable){
        try {
            PackageManager packageManager = XApp.getApp().getPackageManager();
            if (enable){
                packageManager.setComponentEnabledSetting(componentName,PackageManager.COMPONENT_ENABLED_STATE_ENABLED,0);
            }else {
                packageManager.setComponentEnabledSetting(componentName,PackageManager.COMPONENT_ENABLED_STATE_DISABLED,0);
            }
        } catch (Exception e){
            XLog.debug(e.getMessage());
        }
    }
    ```
    - ComponentName mComponentName
    ```
    mComponentName = new ComponentName("cn.xy.windowmanager","cn.xy.windowmanager.MainActivity")
    ```

   - #### 获取APP信息
      - 获取系统所有APP信息
    ```
    /**
     * 获取系统所有APP信息
     * Return the applications' information.
     *
     * @return the applications' information
     */
    public static List<AppInfo> getAppsInfo() {
        List<AppInfo> list = new ArrayList<>();
        PackageManager pm = XApp.getApp().getPackageManager();
        if (pm == null) return list;
        List<PackageInfo> installedPackages = pm.getInstalledPackages(0);
        for (PackageInfo pi : installedPackages) {
            AppInfo ai = getBean(pm, pi);
            if (ai == null) continue;
            list.add(ai);
        }
        return list;
    }
    ```
      - 获取某已安装APP信息
    ```
    /**
     * Return the application's information.
     * <ul>
     * <li>name of package</li>
     * <li>icon</li>
     * <li>name</li>
     * <li>path of package</li>
     * <li>version name</li>
     * <li>version code</li>
     * <li>is system</li>
     * </ul>
     *
     * @param packageName The name of the package.
     * @return the application's information
     */
    public static AppInfo getAppInfo(final String packageName) {
        try {
            PackageManager pm = XApp.getApp().getPackageManager();
            if (pm == null) return null;
            return getBean(pm, pm.getPackageInfo(packageName, 0));
        } catch (PackageManager.NameNotFoundException e) {
            e.printStackTrace();
            return null;
        }
    }
    ```
      - 获取某apk文件信息
       ```
    /**
     * Return the application's package information.
     * 
     * @return the application's package information
     */
    public static XApplication.AppInfo getApkInfo(final String apkFilePath) {
        if (isSpace(apkFilePath)) return null;
        PackageManager pm = XApp.getApp().getPackageManager();
        if (pm == null) return null;
        PackageInfo pi = pm.getPackageArchiveInfo(apkFilePath, 0);
        if (pi == null) return null;
        ApplicationInfo appInfo = pi.applicationInfo;
        appInfo.sourceDir = apkFilePath;
        appInfo.publicSourceDir = apkFilePath;
        return getBean(pm, pi);
    }
    ```
      - getBean
       ```
    private static AppInfo getBean(final PackageManager pm, final PackageInfo pi) {
        if (pi == null) return null;
        ApplicationInfo ai = pi.applicationInfo;
        String packageName = pi.packageName;
        String name = ai.loadLabel(pm).toString();
        Drawable icon = ai.loadIcon(pm);
        String packagePath = ai.sourceDir;
        String versionName = pi.versionName;
        int versionCode = pi.versionCode;
        boolean isSystem = (ApplicationInfo.FLAG_SYSTEM & ai.flags) != 0;
        return new AppInfo(packageName, name, icon, packagePath, versionName, versionCode, isSystem);
    }
    ```