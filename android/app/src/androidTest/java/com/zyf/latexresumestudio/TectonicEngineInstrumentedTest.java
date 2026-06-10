package com.zyf.latexresumestudio;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import android.content.Context;
import android.os.Build;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;
import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public class TectonicEngineInstrumentedTest {
    @Test
    public void bundledTectonicRunsVersionCommand() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        assertEquals("com.zyf.latexresumestudio", context.getPackageName());

        File engine = copyEngineToExecutableFile(context);
        Process process = new ProcessBuilder(engine.getAbsolutePath(), "--version")
            .directory(engine.getParentFile())
            .redirectErrorStream(false)
            .start();

        assertTrue("Tectonic --version timed out", process.waitFor(20, TimeUnit.SECONDS));
        String stdout = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
        String stderr = new String(process.getErrorStream().readAllBytes(), StandardCharsets.UTF_8);
        assertEquals("stderr: " + stderr + " stdout: " + stdout, 0, process.exitValue());
        assertTrue("unexpected version output: " + stdout, stdout.toLowerCase().contains("tectonic"));
    }

    private File copyEngineToExecutableFile(Context context) throws Exception {
        File dir = new File(context.getFilesDir(), "engines-test");
        assertTrue(dir.exists() || dir.mkdirs());

        File engine = new File(dir, "tectonic-test");
        try (InputStream input = context.getAssets().open(resolveEngineAssetPath());
             FileOutputStream output = new FileOutputStream(engine)) {
            byte[] buffer = new byte[1024 * 128];
            int read;
            while ((read = input.read(buffer)) != -1) {
                output.write(buffer, 0, read);
            }
        }
        assertTrue("failed to set executable bit", engine.setExecutable(true, true));
        return engine;
    }

    private String resolveEngineAssetPath() {
        for (String abi : Build.SUPPORTED_ABIS) {
            if ("arm64-v8a".equals(abi)) {
                return "tectonic/tectonic-aarch64-linux-android";
            }
            if ("x86_64".equals(abi)) {
                return "tectonic/tectonic-x86_64-linux-android";
            }
        }
        throw new AssertionError("No supported ABI in " + String.join(",", Build.SUPPORTED_ABIS));
    }
}
