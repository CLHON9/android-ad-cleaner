package aac;

import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.os.Looper;
import java.io.PrintStream;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

/**
 * 按包名打印手机上显示的应用名（跟随系统语言）。只读，不安装、不常驻，打印完就退出。
 * 营销通知清单靠它把包名换成应用名，用户才认得出是哪个软件。
 *
 * 用法：CLASSPATH=/data/local/tmp/aac-labels.dex app_process / aac.Labels 包名…
 * 输出：每个包一行「包名<TAB>应用名」，读不到的应用名为空。
 *
 * app_process 里没有 App 的 Context：照 scrcpy 的做法新建 ActivityThread，取它的系统 Context。
 */
public final class Labels {
    public static void main(String[] args) throws Exception {
        PrintStream out = new PrintStream(System.out, true, "UTF-8");
        PackageManager pm = packageManager();
        for (String pkg : args) {
            String label = "";
            try {
                ApplicationInfo info = pm.getApplicationInfo(pkg, 0);
                CharSequence text = pm.getApplicationLabel(info);
                if (text != null) {
                    label = text.toString().replaceAll("[\\t\\r\\n]+", " ").trim();
                }
            } catch (Throwable ignored) {
                // 未安装、只装在其他用户空间或资源读不出：留空，客户端显示包名
            }
            out.println(pkg + "\t" + label);
        }
    }

    private static PackageManager packageManager() throws Exception {
        if (Looper.getMainLooper() == null) {
            Looper.prepareMainLooper();
        }
        Class<?> cls = Class.forName("android.app.ActivityThread");
        Constructor<?> ctor = cls.getDeclaredConstructor();
        ctor.setAccessible(true);
        Object thread = ctor.newInstance();
        Field current = cls.getDeclaredField("sCurrentActivityThread");
        current.setAccessible(true);
        current.set(null, thread);
        Method system = cls.getDeclaredMethod("getSystemContext");
        return ((Context) system.invoke(thread)).getPackageManager();
    }
}
