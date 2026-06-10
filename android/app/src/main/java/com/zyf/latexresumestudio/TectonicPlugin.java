package com.zyf.latexresumestudio;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

@CapacitorPlugin(name = "Tectonic")
public class TectonicPlugin extends Plugin {
    private static final String ASSET_PATH = "tectonic/tectonic-aarch64-linux-android";
    private static final String ENGINE_DIR = "engines";
    private static final String ENGINE_NAME = "tectonic";

    @PluginMethod
    public void status(PluginCall call) {
        JSObject result = new JSObject();

        try {
            File engine = ensureEngineExecutable();
            ProcessResult version = runEngine(engine, "--version");
            result.put("available", version.exitCode == 0);
            result.put("path", engine.getAbsolutePath());
            result.put("exitCode", version.exitCode);
            result.put("stdout", version.stdout.trim());
            result.put("stderr", version.stderr.trim());
            call.resolve(result);
        } catch (Exception ex) {
            result.put("available", false);
            result.put("error", ex.getMessage());
            call.resolve(result);
        }
    }

    private File ensureEngineExecutable() throws IOException {
        File dir = new File(getContext().getFilesDir(), ENGINE_DIR);
        if (!dir.exists() && !dir.mkdirs()) {
            throw new IOException("无法创建 Tectonic 引擎目录: " + dir.getAbsolutePath());
        }

        File engine = new File(dir, ENGINE_NAME);
        if (!engine.exists() || engine.length() == 0) {
            copyAssetToFile(ASSET_PATH, engine);
        }

        if (!engine.setExecutable(true, true)) {
            throw new IOException("无法设置 Tectonic 可执行权限: " + engine.getAbsolutePath());
        }

        return engine;
    }

    private void copyAssetToFile(String assetPath, File target) throws IOException {
        try (InputStream input = getContext().getAssets().open(assetPath); FileOutputStream output = new FileOutputStream(target)) {
            byte[] buffer = new byte[1024 * 128];
            int read;
            while ((read = input.read(buffer)) != -1) {
                output.write(buffer, 0, read);
            }
        }
    }

    private ProcessResult runEngine(File engine, String... args) throws IOException, InterruptedException {
        String[] command = new String[args.length + 1];
        command[0] = engine.getAbsolutePath();
        System.arraycopy(args, 0, command, 1, args.length);

        Process process = new ProcessBuilder(command)
            .directory(engine.getParentFile())
            .redirectErrorStream(false)
            .start();

        boolean finished = process.waitFor(15, TimeUnit.SECONDS);
        if (!finished) {
            process.destroyForcibly();
            throw new IOException("Tectonic 健康检查超时");
        }

        String stdout = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
        String stderr = new String(process.getErrorStream().readAllBytes(), StandardCharsets.UTF_8);
        return new ProcessResult(process.exitValue(), stdout, stderr);
    }

    private static class ProcessResult {
        final int exitCode;
        final String stdout;
        final String stderr;

        ProcessResult(int exitCode, String stdout, String stderr) {
            this.exitCode = exitCode;
            this.stdout = stdout;
            this.stderr = stderr;
        }
    }
}
