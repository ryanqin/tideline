plugins {
  alias(libs.plugins.android.application)
  alias(libs.plugins.kotlin.android)
  alias(libs.plugins.kotlin.compose)
  alias(libs.plugins.ksp)
}

android {
  namespace = "com.ryanqin.tideline"
  compileSdk = 35

  defaultConfig {
    applicationId = "com.ryanqin.tideline"
    minSdk = 31
    targetSdk = 35
    versionCode = 1
    versionName = "0.1.0"
  }

  buildTypes {
    release {
      isMinifyEnabled = false
      proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
    }
  }

  compileOptions {
    sourceCompatibility = JavaVersion.VERSION_11
    targetCompatibility = JavaVersion.VERSION_11
  }

  kotlinOptions {
    jvmTarget = "11"
  }

  buildFeatures {
    compose = true
  }

  sourceSets {
    named("main") {
      java.srcDirs("src/main/kotlin")
    }
  }

  packaging {
    resources {
      excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
  }
}

dependencies {
  implementation(libs.androidx.core.ktx)
  implementation(libs.androidx.lifecycle.runtime.ktx)
  implementation(libs.androidx.lifecycle.viewmodel.compose)
  implementation(libs.androidx.activity.compose)
  implementation(platform(libs.androidx.compose.bom))
  implementation(libs.androidx.ui)
  implementation(libs.androidx.ui.graphics)
  implementation(libs.androidx.ui.tooling.preview)
  implementation(libs.androidx.material3)
  implementation(libs.material.icon.extended)
  debugImplementation(libs.androidx.ui.tooling)

  implementation(libs.androidx.room.runtime)
  implementation(libs.androidx.room.ktx)
  ksp(libs.androidx.room.compiler)

  implementation(libs.litertlm)

  // GPU backend for LiteRT-LM uses Google Play services TFLite — needed for
  // the fast on-device inference path that hits Adreno on Snapdragon chips.
  // CPU backend works without these but is ~5x slower.
  implementation(libs.play.services.tflite.java)
  implementation(libs.play.services.tflite.gpu)
  implementation(libs.play.services.tflite.support)

  // Phase 5a live capture: in-app viewfinder + shutter (point at a menu,
  // snap, translate) instead of bouncing through the system photo picker.
  implementation(libs.androidx.camera.core)
  implementation(libs.androidx.camera.camera2)
  implementation(libs.androidx.camera.lifecycle)
  implementation(libs.androidx.camera.view)
  // Gallery-picked photos carry EXIF orientation that BitmapFactory ignores;
  // needed so persisted recall photos aren't stored sideways.
  implementation(libs.androidx.exifinterface)

  // Geometry source for photo-word masks (annotation overlays): on-device
  // OCR supplies the pixel boxes of words the LLM has already read and
  // translated - ML Kit owns WHERE, the model owns WHAT (engineering
  // carries, model garnishes). Latin recognizer only for now.
  implementation(libs.mlkit.text.recognition)

  testImplementation(libs.junit)
}
