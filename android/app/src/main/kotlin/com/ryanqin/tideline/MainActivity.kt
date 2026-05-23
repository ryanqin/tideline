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
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import android.os.Build
import com.ryanqin.tideline.ui.TidelineScreen

class MainActivity : ComponentActivity() {
  override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    setContent {
      val ctx = LocalContext.current
      val colors = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        dynamicLightColorScheme(ctx)
      } else {
        lightColorScheme()
      }
      MaterialTheme(colorScheme = colors) {
        Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
          TidelineScreen()
        }
      }
    }
  }
}
