---
title: WindowManager基础
date: 2020-05-28 09:29:19
tags: WindowManager
categories: Android
---
### 一.代码位置
[XTester-WindowManager](https://github.com/itemuse/XTester/tree/master/windowmanager)
[xlib-Screen](https://github.com/itemuse/XLib/blob/master/library/src/main/java/cn/xy/library/util/screen/XScreen.java)
此文是在此基础上做的讲解,用于加深印象

### 二.WindowManager介绍
Android为我们提供的用于与窗口管理器进行交互的一个API！我们都知道App的界面都是 由一个个的Acitivty组成，而Activity又由View组成，当我们想显示一个界面的时候， 第一时间想起的是:Activity，对吧？又或者是Dialog和Toast。

但是有些情况下，前面这三者可能满足不了我们的需求，比如我们仅仅是一个简单的显示 用Activity显得有点多余了，而Dialog又需要Context对象，Toast又不可以点击... 对于以上的情况我们可以利用WindowManager这个东东添加View到屏幕上， 或者从屏幕上移除View！他就是管理Android窗口机制的一个接口，显示View的最底层！

### 三.如何获得WindowManager实例
   - #### 获得WindowManager对象:
```
WindowManager wManager = getApplicationContext().getSystemService(Context. WINDOW_ SERVICE);
```
   - #### 获得WindowManager.LayoutParams对象，为后续操作做准备
```
WindowManager.LayoutParams wmParams=new WindowManager.LayoutParams();
```

### 四.WindowManager使用实例：

   - #### 实例1：获取屏幕宽高
```
    /**
     * Return the width of screen, in pixel.
     *
     * @return the width of screen, in pixel
     */
    public static int getScreenWidth() {
        WindowManager wm = (WindowManager) getApp().getSystemService(Context.WINDOW_SERVICE);
        if (wm == null) return -1;
        Point point = new Point();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.JELLY_BEAN_MR1) {
            wm.getDefaultDisplay().getRealSize(point);
        } else {
            wm.getDefaultDisplay().getSize(point);
        }
        return point.x;
    }

    /**
     * Return the height of screen, in pixel.
     *
     * @return the height of screen, in pixel
     */
    public static int getScreenHeight() {
        WindowManager wm = (WindowManager) getApp().getSystemService(Context.WINDOW_SERVICE);
        if (wm == null) return -1;
        Point point = new Point();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.JELLY_BEAN_MR1) {
            wm.getDefaultDisplay().getRealSize(point);
        } else {
            wm.getDefaultDisplay().getSize(point);
        }
        return point.y;
    }
    ```
获取应用宽高
    ```
    /**
     * Return the application's width of screen, in pixel.
     *
     * @return the application's width of screen, in pixel
     */
    public static int getAppScreenWidth() {
        WindowManager wm = (WindowManager) getApp().getSystemService(Context.WINDOW_SERVICE);
        if (wm == null) return -1;
        Point point = new Point();
        wm.getDefaultDisplay().getSize(point);
        return point.x;
    }

    /**
     * Return the application's height of screen, in pixel.
     *
     * @return the application's height of screen, in pixel
     */
    public static int getAppScreenHeight() {
        WindowManager wm = (WindowManager) getApp().getSystemService(Context.WINDOW_SERVICE);
        if (wm == null) return -1;
        Point point = new Point();
        wm.getDefaultDisplay().getSize(point);
        return point.y;
    }
```
![](/blog/assets/2021-03-08-WindowManager%E5%9F%BA%E7%A1%80/img1.jpg)

   - #### 实例2：设置窗口全屏显示
```
getWindow().setFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN,
                WindowManager.LayoutParams.FLAG_FULLSCREEN);
        getSupportActionBar().hide();
```
运行结果：
![](/blog/assets/2021-03-08-WindowManager%E5%9F%BA%E7%A1%80/img2.jpg)

   - #### 实例3：保持屏幕常亮
```
    /**
     * @param activity
     * @param keepScreenOn 是否开启屏幕常亮
     */
    public void setKeepScreenOn(Activity activity, boolean keepScreenOn) {
        if(keepScreenOn){
            activity.getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        }else{
            activity.getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        }
    }
```

   - #### 实例4：简单悬浮框的实现
实现代码：
一个触摸图标工具类：EasyTouchView.class
```
package cn.xy.windowmanager;

import android.annotation.SuppressLint;
import android.content.Context;
import android.graphics.PixelFormat;
import android.os.Build;
import android.util.DisplayMetrics;
import android.util.Log;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;

public class EasyTouchView{

    public static final String TAG = "EasyTouch";
    private static EasyTouchView mEasyTouchView;
    private Context mContext;

    public static EasyTouchView getInstance() {
        if (mEasyTouchView == null) {
            mEasyTouchView = new EasyTouchView();
        }
        return mEasyTouchView;
    }

    private WindowManager mWindowManager;
    private int width, height;
    private double stateHeight;
    private WindowManager.LayoutParams layoutParams;
    private Button iconView;
    private float startX = 0, startY = 0;
    private float startRawX = 0, startRawY = 0;
    private int iconViewX = 0, iconViewY = 0;
    private boolean isIconView = false;

    private DisplayMetrics mDisplayMetrics;

    public void initEasyTouch(Context mContext, DisplayMetrics displayMetrics) {
        this.mDisplayMetrics = displayMetrics;
        this.mContext = mContext;
        width = mDisplayMetrics.widthPixels;
        height = mDisplayMetrics.heightPixels;
        stateHeight = Math.ceil(25 * displayMetrics.density);
        createWM();
    }

    private void createWM() {
        mWindowManager = (WindowManager) mContext.getSystemService(Context.WINDOW_SERVICE);
        layoutParams = new WindowManager.LayoutParams();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M){
            layoutParams.type = WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY;
        }else {
            layoutParams.type =  WindowManager.LayoutParams.TYPE_SYSTEM_ALERT;
        }
        layoutParams.format = PixelFormat.TRANSLUCENT;
        layoutParams.flags = WindowManager.LayoutParams.FLAG_IGNORE_CHEEK_PRESSES | WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE;

    }

    @SuppressLint("ClickableViewAccessibility")
    public void addIconView() {
        if (isIconView) {
            return;
        }
        isIconView = true;
        if (iconView == null) {
            iconView = new Button(mContext);
            iconView.setBackgroundResource(R.mipmap.ic_launcher);
            iconView.setOnTouchListener(new View.OnTouchListener() {

                @Override
                public boolean onTouch(View v, MotionEvent event) {
                    float rawX = event.getRawX();
                    float rawY = (float) (event.getRawY() - stateHeight);

                    int sumX = (int) (rawX - startRawX);
                    int sumY = (int) (event.getRawY() - startRawY);

                    switch (event.getAction()) {
                    case MotionEvent.ACTION_DOWN:
                        Log.i("Log", "Action_Down");
                        startX = event.getX();
                        startY = event.getY();
                        startRawX = event.getRawX();
                        startRawY = event.getRawY();

                        layoutParams.alpha = 1f;
                        mWindowManager.updateViewLayout(iconView, layoutParams);
                        break;
                    case MotionEvent.ACTION_UP:
/*                        layoutParams.alpha = 0.6f;
                        mWindowManager.updateViewLayout(iconView, layoutParams);
                        if (sumX > -10 && sumX < 10 && sumY > -10 && sumY < 10) {
                            removeIcon();
                        } else {
                            float endRawX = rawX - startX;
                            float endRawY = rawY - startY;
                            if (endRawX < width / 2) {
                                if (endRawX > endRawY) {
                                    if (rawY > iconView.getHeight() * 2) {
                                        updateIconViewPosition(endRawX, endRawY);
                                    } else {
                                        updateIconViewPosition(endRawX, 0);
                                    }
                                } else if (endRawX > height - event.getRawY() - 98) {
                                    if ((float) (height - stateHeight - endRawY - 98) > iconView.getHeight() * 2) {
                                        updateIconViewPosition(endRawX, endRawY);
                                    } else {
                                        updateIconViewPosition(endRawX, (float) (height - stateHeight - 98));

                                    }

                                } else {
                                    if (endRawX > iconView.getWidth() * 2) {
                                        updateIconViewPosition(endRawX, endRawY);

                                    } else {
                                        updateIconViewPosition(0, endRawY);

                                    }

                                }
                            } else {
                                if (width - endRawX - 98 > endRawY) {
                                    if (rawY > iconView.getHeight() * 2) {
                                        updateIconViewPosition(endRawX, endRawY);
                                    } else {
                                        updateIconViewPosition(endRawX, 0);

                                    }

                                } else if (width - endRawX - 98 > height - event.getRawY() - 98) {
                                    if ((float) (height - stateHeight - endRawY - 98) > iconView.getHeight() * 2) {
                                        updateIconViewPosition(endRawX, endRawY);
                                    } else {
                                        updateIconViewPosition(endRawX, (float) (height - stateHeight - 98));
                                    }

                                } else {
                                    if (width - endRawX - 98 > iconView.getWidth() * 2) {
                                        updateIconViewPosition(endRawX, endRawY);

                                    } else {
                                        updateIconViewPosition(width, endRawY);
                                    }

                                }
                            }
                        }
                        startX = 0;
                        startY = 0;
                        startRawX = 0;
                        startRawY = 0;*/
                        break;
                    case MotionEvent.ACTION_MOVE:
                        if (sumX < -10 || sumX > 10 || sumY < -10 || sumY > 10) {
                            updateIconViewPosition(rawX - startX, rawY - startY);
                        }
                        break;
                    default:
                        break;
                    }
                    return true;
                }
            });
        }
        layoutParams.alpha = 0.5f;
        layoutParams.x = iconViewX;
        layoutParams.y = iconViewY;
        layoutParams.width = 170;
        layoutParams.height = 170;
        layoutParams.gravity = Gravity.LEFT | Gravity.TOP;
        mWindowManager.addView(iconView, layoutParams);
    }

    private void updateIconViewPosition(float x, float y) {
        iconViewX = (int) x;
        iconViewY = (int) y;
        layoutParams.x = (int) x;
        layoutParams.y = (int) y;
        mWindowManager.updateViewLayout(iconView, layoutParams);
    }

    public void removeIcon() {
        if (isIconView && iconView != null) {
            mWindowManager.removeView(iconView);
            isIconView = false;
        }
    }
}

```
开关控制
```
    public void onClick(View view){
        switch (view.getId()){
            case R.id.open:
                EasyTouchView.getInstance().addIconView();
                break;
            case R.id.close:
                EasyTouchView.getInstance().removeIcon();
                break;
        }
    }
```
接着AndroidManifest.xml加上权限，以及为MainService进行注册：
```
    <uses-permission android:name="android.permission.SYSTEM_ALERT_WINDOW"/>
```
运行效果图：
![](/blog/assets/2021-03-08-WindowManager%E5%9F%BA%E7%A1%80/img3.gif)
