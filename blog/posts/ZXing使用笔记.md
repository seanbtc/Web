---
title: ZXing使用笔记
date: 2016-02-25 21:46:47
tags: ZXing
categories: Android
---

### 一.达到的效果
![](/blog/assets/ZXing%E4%BD%BF%E7%94%A8%E7%AC%94%E8%AE%B0/img.gif)

### 二.使用到的依赖包：
此库为Zxing的精简版，可以很容易在csdn下载，就不过多做介绍；
![](/blog/assets/ZXing%E4%BD%BF%E7%94%A8%E7%AC%94%E8%AE%B0/img1.png)

### 三.简单实现
将此库导入项目到eclipse后，新建一个项目关联它，布局文件只需一个butoon，MainActivity代码如下：
```
package com.Even.demo_zing;
 
import com.zxing.activity.CaptureActivity;
 
public class MainActivity extends Activity implements OnClickListener{
	private Button button1;
 
	@Override
	protected void onCreate(Bundle savedInstanceState) {
		super.onCreate(savedInstanceState);
		setContentView(R.layout.activity_main);
		button1 = (Button) findViewById(R.id.button1);
		button1.setOnClickListener(this);
	}
 
	@Override
	public void onClick(View v) {
		//跳转至ZXing自带的扫码界面操作
		Intent intent=new Intent(this,CaptureActivity.class);
		startActivityForResult(intent,0);
	}
	
	@Override
	protected void onActivityResult(int requestCode, int resultCode, Intent data) {
		if(resultCode==Activity.RESULT_OK){
            //重写result，获得扫描出来的内容：
			String result=data.getExtras().getString("result");
			Toast.makeText(this, result, 1).show();
		}
	}
}
```
权限
```
<uses-permission android:name="android.permission.CAMERA"/>
<uses-permission android:name="android.permission.VIBRATE"/>
```
清单配置文件中配置CaptureActivity
```
<activity
            android:configChanges="orientation|keyboardHidden"
            android:name="com.zxing.activity.CaptureActivity"
            android:screenOrientation="portrait"
            android:theme="@android:style/Theme.NoTitleBar.Fullscreen"
            android:windowSoftInputMode="stateAlwaysHidden" >
        </activity>
```
这样就可以简单地实现扫描功能了！

### 四.生成二维码/条形码
代码：
[XTester-zxing](https://github.com/itemuse/XTester/tree/master/zxing)
更新时间:23:59 2021/3/18
```
    //绘制二维码
    public Bitmap QrCode(String s) throws Exception{
        //二维码QR_CODE
        BarcodeFormat fomt=BarcodeFormat.QR_CODE;
        //编码转换
        String a=new String(s.getBytes("utf-8"),"ISO-8859-1");
        BitMatrix matrix=new MultiFormatWriter().encode(a, fomt, width, height);
        int width=matrix.getWidth();
        int height=matrix.getHeight();
        int[] pixel=new int[width*height];
        for(int i=0;i<height;i++){
            for(int j=0;j<width;j++){
                if(matrix.get(j,i))
                    pixel[i*width+j]=0xff000000;
            }
        }
        Bitmap bmap=Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888);
        bmap.setPixels(pixel, 0, width, 0, 0, width, height);
        return bmap;
    }
    //绘制条形码
    public Bitmap BarCode(String ss) throws Exception{
        //条形码CODE_128
        BarcodeFormat fomt=BarcodeFormat.CODE_128;
        BitMatrix matrix=new MultiFormatWriter().encode(ss, fomt, width, height);
        int width=matrix.getWidth();
        int height=matrix.getHeight();
        int[] pixel=new int[width*height];
        for(int i=0;i<height;i++){
            for(int j=0;j<width;j++){
                if(matrix.get(j,i))
                    pixel[i*width+j]=0xff000000;
            }
        }
        Bitmap bmapp=Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888);
        bmapp.setPixels(pixel, 0, width, 0, 0, width, height);
        return bmapp;
    }
```
效果
![](/blog/assets/ZXing%E4%BD%BF%E7%94%A8%E7%AC%94%E8%AE%B0/img3.gif)