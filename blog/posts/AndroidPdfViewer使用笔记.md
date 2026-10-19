---
title: AndroidPdfViewer使用笔记
date: 2021-03-19 00:15:38
tags: PDF
categories: Android
---

### 一.代码
- [AndroidPdfViewer](https://github.com/barteksc/AndroidPdfViewer)
- [XTester-pdf](https://github.com/itemuse/XTester/tree/master/pdf)

### 二.效果图
![](/blog/assets/AndroidPdfViewer%E4%BD%BF%E7%94%A8%E7%AC%94%E8%AE%B0/img.gif)

### 三.实现
- 准备
   - build.gradle
   ```
    implementation 'com.github.barteksc:android-pdf-viewer:3.2.0-beta.1'
   ```

   - 权限
   ```
    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" />
    <uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" />
    ```
    Android10以上版本要在application中增加
    ```
    android:requestLegacyExternalStorage="true"
    ```
    否则READ_EXTERNAL_STORAGE权限无效

- 实现
   - 布局
   ```
   <?xml version="1.0" encoding="utf-8"?>
<FrameLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/activity_main"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:orientation="vertical">

    <com.github.barteksc.pdfviewer.PDFView
        android:id="@+id/pdfView"
        android:layout_width="match_parent"
        android:layout_height="match_parent"/>

</FrameLayout>
```

   - java
   ```
   PDFView.Configurator configurator;
    public void LoadFile(){
        File newFile = new File(Path);
        File newFile_ = new File(Path_);
        if(newFile!=null && newFile.exists() && newFile.canRead()){
            configurator = pdfView.fromFile(newFile);
        }else if(newFile_!=null && newFile_.exists() && newFile.canRead()){
            configurator = pdfView.fromFile(newFile_);
        }else{
            configurator = pdfView.fromAsset("TWPDF.pdf");
        }
        showPDFUI();
    }

    ...

     /**
     *     .pages(0, 2, 1, 3, 3, 3) // 默认显示所有页面
     *     .enableSwipe(true) // 允许使用滑动来阻止改变页面
     *     .swipeHorizontal(false) //是否横向滑动显示
     *     .enableDoubletap(true)
     *     .defaultPage(0) //默认进入的页面
     *     // 允许在当前页面上画一些东西，通常在屏幕中间可见
     *     .onDraw(onDrawListener)
     *     // 允许在所有页面上画一些东西，单独为每一页。仅对可见页面调用
     *     .onDrawAll(onDrawListener)
     *     .onLoad(onLoadCompleteListener) // 加载文档并开始呈现后调用
     *     .onPageChange(onPageChangeListener)
     *     .onPageScroll(onPageScrollListener)
     *     .onError(onErrorListener)
     *     .onPageError(onPageErrorListener)
     *     .onRender(onRenderListener) // 第一次呈现文档后调用
     *     // 点击一次调用，如果已处理则返回true，如果切换滚动句柄可见性返回false
     *     .onTap(onTapListener)
     *     .onLongPress(onLongPressListener)
     *     .enableAnnotationRendering(false) // 呈现注释(例如注释、颜色或表单)
     *     .password(null)
     *     .scrollHandle(null)
     *     .enableAntialiasing(true) // 在低分辨率屏幕上改进渲染
     *     // dp中页面之间的间距。要定义间距颜色，设置视图背景
     *     .spacing(0)
     *     .autoSpacing(false) // 添加动态间距以适应屏幕上的每个页面
     *     .linkHandler(DefaultLinkHandler)
     *     .pageFitPolicy(FitPolicy.WIDTH) // 模式以适应视图中的页面
     *     .fitEachPage(false) // 将每个页面适应于视图，否则较小的页面相对于最大的页面缩放
     *     .pageSnap(false) // 将页面对齐到屏幕边界
     *     .pageFling(false) // 在ViewPager这样的单一页面上做一个短暂的改变
     *     .nightMode(false) // 切换夜间模式
     */
    private void showPDFUI(){
        configurator.enableSwipe(true)
                .swipeHorizontal(true)
                .enableDoubletap(false)
                .fitEachPage(false)
                .autoSpacing(true)
                .pageFitPolicy(FitPolicy.WIDTH)
                .onLoad(new OnLoadCompleteListener() {
                    @Override
                    public void loadComplete(int nbPages) {
                    }
                })
                .onPageChange(new OnPageChangeListener() {

                    @Override
                    public void onPageChanged(int page, int pageCount) {
                        mPageCount = pageCount;
                        mPpagerIndex = page;
                    }
                })
                .enableAnnotationRendering(false)
                .password(null)
                .scrollHandle(null)
                .enableAntialiasing(true)
                .spacing(0)
                .pageSnap(true)
                .nightMode(true)
                .load();
    }
   ```
跳转至指定页面的方法
```
/**
     * Go to the given page.
     *
     * @param page Page index.
     */
    public void jumpTo(int page, boolean withAnimation) {
    }
        ```
        