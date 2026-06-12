/*
 * Tideline — local-first translation agent.
 * Standalone Android shell, extracted from ryanqin/gallery@tideline fork on 2026-05-22.
 */

package com.ryanqin.tideline

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier
import androidx.lifecycle.ViewModelProvider
import com.ryanqin.tideline.ui.TidelineScreen
import com.ryanqin.tideline.ui.TidelineTranslateViewModel
import com.ryanqin.tideline.ui.theme.TidelineTheme

class MainActivity : ComponentActivity() {
  override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    // Dev loop (debug builds): a file name in the app's external files dir,
    // passed as an intent extra, runs through the image→translation pipeline
    // once the engine is ready — drives image-path iteration over adb without
    // anyone pointing a camera:
    //   adb shell am start -n com.ryanqin.tideline/.MainActivity \
    //     --es tideline.debug_image tideline_test.jpg
    val debuggable =
      (applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0
    if (debuggable) {
      val vm = ViewModelProvider(this)[TidelineTranslateViewModel::class.java]
      // Same ViewModelStoreOwner as the composable's viewModel() — one VM.
      intent?.getStringExtra("tideline.debug_image")?.let { vm.queueDebugImage(it) }
      intent?.getStringExtra("tideline.debug_audio")?.let { vm.queueDebugAudio(it) }
    }
    setContent {
      TidelineTheme {
        Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
          TidelineScreen()
        }
      }
    }
  }
}
