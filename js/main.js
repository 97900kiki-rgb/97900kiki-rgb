// ==================== Header scroll effect ====================
const header = document.getElementById('site-header');
function handleHeaderScroll() {
  if (window.scrollY > 20) {
    header.classList.add('scrolled');
  } else {
    header.classList.remove('scrolled');
  }
}
window.addEventListener('scroll', handleHeaderScroll);
handleHeaderScroll();

// ==================== Mobile menu ====================
const menuBtn = document.getElementById('menu-btn');
const mobileMenu = document.getElementById('mobile-menu');
menuBtn.addEventListener('click', () => {
  mobileMenu.classList.toggle('hidden');
  const icon = menuBtn.querySelector('i');
  if (mobileMenu.classList.contains('hidden')) {
    icon.classList.remove('fa-xmark');
    icon.classList.add('fa-bars');
  } else {
    icon.classList.remove('fa-bars');
    icon.classList.add('fa-xmark');
  }
});
document.querySelectorAll('#mobile-menu a').forEach(link => {
  link.addEventListener('click', () => {
    mobileMenu.classList.add('hidden');
    const icon = menuBtn.querySelector('i');
    icon.classList.remove('fa-xmark');
    icon.classList.add('fa-bars');
  });
});

// ==================== Reveal on scroll ====================
const revealEls = document.querySelectorAll('.reveal');
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('visible');
      revealObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.1, rootMargin: '0px 0px -50px 0px' });
revealEls.forEach(el => revealObserver.observe(el));

// Safety net: ensure content is never permanently hidden even if the
// observer fails to fire (e.g. very fast full-page renders/screenshots).
setTimeout(() => {
  revealEls.forEach(el => el.classList.add('visible'));
}, 1800);

// ==================== Outfit registration ====================
const coordiFileInput = document.getElementById('coordi-file');
const uploadPreview = document.getElementById('upload-preview');
const selectedImage = document.getElementById('selected-image');
const savedCountEl = document.getElementById('saved-count');
const registerButton = document.getElementById('register-button');
const recommendButton = document.getElementById('recommend-button');
const saveStatus = document.getElementById('save-status');
const moodChips = document.querySelectorAll('.tag-chip');
const coordiGallery = document.getElementById('coordi-gallery');
const coordiModal = document.getElementById('coordi-modal');
const modalImage = document.getElementById('modal-image');
const closeModalBtn = document.getElementById('close-modal');
const recommendationPanel = document.getElementById('recommendation-panel');

let selectedMood = '클래식';

function getStoredItems() {
  try {
    return JSON.parse(localStorage.getItem('ai-codi-items') || '[]');
  } catch {
    return [];
  }
}

function updateSavedCount() {
  const items = getStoredItems();
  const count = items.length + 120;
  if (savedCountEl) {
    savedCountEl.textContent = count + '+';
  }
}

function getRecommendationImage(item, index) {
  return item?.imageData || `images/outfits/outfit-${String((index % 12) + 1).padStart(3, '0')}.png`;
}

function generateRecommendationCards() {
  const items = getStoredItems();
  const mood = document.getElementById('coordi-situation')?.value || '데이트';
  const situation = document.getElementById('coordi-situation')?.value || '데이트';
  const category = document.getElementById('coordi-category')?.value || '상의';

  const ruleSet = {
    클래스: {
      label: '출근 준비',
      title: '클래식 스마트 캐주얼',
      description: '정돈된 상의와 깔끔한 하의 조합으로 세련된 업무 분위기를 살려줍니다.',
      chips: ['화이트 셔츠', '블랙 슬랙스', '로퍼']
    },
    캐주얼: {
      label: '데일리',
      title: '캐주얼 편안함',
      description: '부드러운 라인과 가벼운 감성으로 일상 속에서 부담 없이 입기 좋습니다.',
      chips: ['오버셔츠', '청바지', '화이트 스니커즈']
    },
    프레시: {
      label: '주말',
      title: '프레시 에너지 룩',
      description: '밝은 톤과 경쾌한 디테일로 주말 분위기를 한껏 살려줍니다.',
      chips: ['라이트 니트', '와이드 팬츠', '스니커즈']
    },
    시크: {
      label: '데이트',
      title: '시크 고급 연출',
      description: '어두운 톤과 구조적인 실루엣으로 차분한 자신감을 표현합니다.',
      chips: ['블랙 니트', '슬림 팬츠', '레더 부츠']
    },
    데일리: {
      label: '평일',
      title: '데일리 무난 완성',
      description: '쉽게 매치하면서도 안정적이고 무난한 스타일을 완성합니다.',
      chips: ['베이지 니트', '청바지', '로퍼']
    }
  };

  const templates = [
    ruleSet[selectedMood] || ruleSet['클래식'],
    ruleSet[items[Math.max(0, items.length - 1)]?.mood] || ruleSet['캐주얼'],
    ruleSet[items[Math.max(0, items.length - 2)]?.mood] || ruleSet['프레시']
  ];

  if (!items.length) {
    return templates.map((template, index) => `
      <div class="recommend-card">
        <img src="${getRecommendationImage(null, index)}" alt="${template.title}" class="recommend-image">
        <div class="recommend-content">
        <span class="recommend-badge">${template.label}</span>
        <h4>${template.title}</h4>
        <p>${template.description}</p>
        <div class="recommend-list">
          ${template.chips.map(chip => `<span class="recommend-pill">${chip}</span>`).join('')}
        </div>
        </div>
      </div>
    `).join('');
  }

  return items.slice().reverse().slice(0, 3).map((item, index) => {
    const template = templates[index] || templates[0];
    const moodText = item.mood || selectedMood;
    const situationText = item.situation || situation;
    const categoryText = item.category || category;
    return `
      <div class="recommend-card">
        <img src="${getRecommendationImage(item, index)}" alt="${item.name || template.title}" class="recommend-image">
        <div class="recommend-content">
        <span class="recommend-badge">${template.label}</span>
        <h4>${item.name || template.title}</h4>
        <p>${item.note || template.description}</p>
        <div class="recommend-list">
          <span class="recommend-pill">${categoryText}</span>
          <span class="recommend-pill">${situationText}</span>
          <span class="recommend-pill">${moodText}</span>
        </div>
        </div>
      </div>
    `;
  }).join('');
}

function renderRecommendations() {
  if (!recommendationPanel) return;
  recommendationPanel.innerHTML = generateRecommendationCards();
}

function renderGallery() {
  if (!coordiGallery) return;

  const items = getStoredItems();
  if (!items.length) {
    coordiGallery.innerHTML = `
      <div class="md:col-span-2 xl:col-span-4 rounded-2xl border border-dashed border-white/10 bg-white/3 p-8 text-center text-white/50">
        아직 등록된 코디가 없습니다. 첫 번째 코디를 저장해보세요.
      </div>
    `;
    renderRecommendations();
    return;
  }

  coordiGallery.innerHTML = items.slice().reverse().map(item => `
    <div class="coordi-card">
      <div class="h-48 overflow-hidden bg-[#1a1029]">
        ${item.imageData ? `<img src="${item.imageData}" alt="${item.name}" class="w-full h-full object-cover">` : `<div class="w-full h-full flex items-center justify-center text-white/35"><i class="fa-solid fa-shirt text-3xl"></i></div>`}
      </div>
      <div class="p-4">
        <div class="flex items-center justify-between gap-3">
          <h4 class="font-semibold text-white">${item.name}</h4>
          <span class="rounded-full border border-fuchsia-400/30 bg-fuchsia-500/10 px-2 py-1 text-[10px] font-semibold text-fuchsia-200">${item.mood}</span>
        </div>
        <div class="mt-3 flex gap-2 flex-wrap text-[11px] uppercase tracking-wider text-white/55">
          <span class="rounded-full border border-white/10 px-2 py-1">${item.category}</span>
          <span class="rounded-full border border-white/10 px-2 py-1">${item.situation}</span>
        </div>
        <p class="mt-3 text-sm text-white/60 line-clamp-3">${item.note || '추가 메모가 없습니다.'}</p>
        <div class="coordi-actions">
          <button class="coordi-action-btn preview-btn" data-id="${item.id}" type="button">미리보기</button>
          <button class="coordi-action-btn delete" data-delete-id="${item.id}" type="button">삭제</button>
        </div>
      </div>
    </div>
  `).join('');

  coordiGallery.querySelectorAll('.preview-btn').forEach(button => {
    button.addEventListener('click', () => {
      const id = Number(button.dataset.id);
      const item = getStoredItems().find(entry => entry.id === id);
      if (!item || !item.imageData) return;
      if (modalImage) modalImage.src = item.imageData;
      if (coordiModal) coordiModal.classList.remove('hidden');
      if (coordiModal) coordiModal.classList.add('flex');
    });
  });

  coordiGallery.querySelectorAll('[data-delete-id]').forEach(button => {
    button.addEventListener('click', () => {
      const id = Number(button.dataset.deleteId);
      const remaining = getStoredItems().filter(item => item.id !== id);
      localStorage.setItem('ai-codi-items', JSON.stringify(remaining));
      updateSavedCount();
      renderGallery();
      renderRecommendations();
      if (saveStatus) {
        saveStatus.textContent = '코디가 삭제되었습니다.';
        saveStatus.className = 'mt-4 min-h-[1.5rem] text-sm text-rose-300';
      }
    });
  });

  renderRecommendations();
}

if (coordiFileInput) {
  coordiFileInput.addEventListener('change', (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (loadEvent) => {
      const dataUrl = loadEvent.target?.result;
      if (!dataUrl) return;
      selectedImage.src = dataUrl;
      uploadPreview.classList.remove('hidden');
      if (saveStatus) {
        saveStatus.textContent = `${file.name} 업로드 완료`;
        saveStatus.className = 'mt-4 min-h-[1.5rem] text-sm text-emerald-300';
      }
    };
    reader.readAsDataURL(file);
  });
}

moodChips.forEach(chip => {
  chip.addEventListener('click', () => {
    moodChips.forEach(item => item.classList.remove('active'));
    chip.classList.add('active');
    selectedMood = chip.dataset.tag || '클래식';
  });
});

if (registerButton) {
  registerButton.addEventListener('click', () => {
    const name = document.getElementById('coordi-name')?.value || '새로운 코디';
    const category = document.getElementById('coordi-category')?.value || '상의';
    const situation = document.getElementById('coordi-situation')?.value || '데이트';
    const note = document.getElementById('coordi-note')?.value || '';
    const imageData = selectedImage?.src || '';

    const item = {
      id: Date.now(),
      name,
      category,
      situation,
      mood: selectedMood,
      note,
      imageData,
      createdAt: new Date().toISOString()
    };

    const existing = getStoredItems();
    existing.push(item);
    localStorage.setItem('ai-codi-items', JSON.stringify(existing));
    updateSavedCount();
    renderGallery();
    renderRecommendations();

    if (saveStatus) {
      saveStatus.textContent = `${name} 등록 완료! AI 추천에 반영되었습니다.`;
      saveStatus.className = 'mt-4 min-h-[1.5rem] text-sm text-fuchsia-300';
    }
  });
}

if (recommendButton) {
  recommendButton.addEventListener('click', () => {
    renderRecommendations();
    if (saveStatus) {
      saveStatus.textContent = 'AI 추천을 다시 생성했습니다.';
      saveStatus.className = 'mt-4 min-h-[1.5rem] text-sm text-emerald-300';
    }
  });
}

if (closeModalBtn) {
  closeModalBtn.addEventListener('click', () => {
    if (coordiModal) {
      coordiModal.classList.add('hidden');
      coordiModal.classList.remove('flex');
    }
  });
}

if (coordiModal) {
  coordiModal.addEventListener('click', (event) => {
    if (event.target === coordiModal) {
      coordiModal.classList.add('hidden');
      coordiModal.classList.remove('flex');
    }
  });
}

renderGallery();
renderRecommendations();
updateSavedCount();
