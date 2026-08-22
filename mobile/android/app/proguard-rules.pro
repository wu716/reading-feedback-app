# WebView 套壳，暂不开启混淆
-keepclassmembers class com.shuran.app.ReminderJsBridge {
    @android.webkit.JavascriptInterface <methods>;
}
