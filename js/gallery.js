/* ============================================================
   AI CODI - 코디 갤러리 (Outfit Gallery)
   - 코디 등록/수정 (사진 업로드 포함)
   - 다른 사람이 별점/코멘트를 남길 수 있는 리뷰 기능
   ============================================================ */

(function () {
  'use strict';

  const OCCASIONS = ['데일리', '오피스', '데이트', '여행', '파티', '운동'];

  let allOutfits = [];
  let allRatings = [];
  let currentFilter = '전체';
  let currentSort = 'latest';
  let currentDetailOutfitId = null;
  let editingOutfitId = null;
  let pendingImageDataUrl = null;
  let selectedRatingValue = 0;
  let selectedColors = [];

  // ---------- 퍼스널 컬러 팔레트 ----------
  const PALETTE_BY_TONE = {
    '웜톤': [
      { hex: '#F9E4C8', name: '피치 크림' },
      { hex: '#F4A261', name: '피치 오렌지' },
      { hex: '#E76F51', name: '테라코타' },
      { hex: '#D4A373', name: '카멜' },
      { hex: '#E9C46A', name: '워밍 옐로우' },
      { hex: '#A0522D', name: '러스트 브라운' },
      { hex: '#C9B89A', name: '누드 베이지' },
      { hex: '#8B6914', name: '머스타드 골드' },
      { hex: '#D4C5A9', name: '샌드 베이지' },
      { hex: '#7D5A3C', name: '다크 카멜' },
      { hex: '#B5835A', name: '코퍼 브라운' },
      { hex: '#F0E6D3', name: '아이보리' },
    ],
    '쿨톤': [
      { hex: '#DCE8F5', name: '라이트 블루' },
      { hex: '#A8D8EA', name: '스카이 블루' },
      { hex: '#457B9D', name: '스틸 블루' },
      { hex: '#1D3557', name: '네이비' },
      { hex: '#E8C8D4', name: '로즈 핑크' },
      { hex: '#C77DFF', name: '라벤더' },
      { hex: '#7B2D8B', name: '딥 퍼플' },
      { hex: '#6D6875', name: '모브 그레이' },
      { hex: '#2C3E50', name: '차콜 네이비' },
      { hex: '#F8F9FA', name: '퓨어 화이트' },
      { hex: '#3D405B', name: '딥 인디고' },
      { hex: '#80B3A0', name: '민트 그린' },
    ],
    '뉴트럴': [
      { hex: '#F5F0EB', name: '오프 화이트' },
      { hex: '#E8E0D5', name: '크림' },
      { hex: '#D9D2C5', name: '베이지' },
      { hex: '#C5BDB0', name: '웜 그레이' },
      { hex: '#8F8577', name: '그레이지' },
      { hex: '#6B6560', name: '올리브 그레이' },
      { hex: '#4F4A43', name: '차콜 브라운' },
      { hex: '#2C2C2C', name: '다크 차콜' },
      { hex: '#A8B5A2', name: '세이지 그린' },
      { hex: '#BDB2A1', name: '그레이 베이지' },
      { hex: '#7C7264', name: '토프' },
      { hex: '#FFFFFF', name: '화이트' },
    ]
  };

  // ---------- DOM refs ----------
  const galleryGrid = document.getElementById('gallery-grid');
  const galleryLoading = document.getElementById('gallery-loading');
  const galleryEmpty = document.getElementById('gallery-empty');
  const statOutfitCount = document.getElementById('stat-outfit-count');
  const statReviewCount = document.getElementById('stat-review-count');
  const statAvgRating = document.getElementById('stat-avg-rating');
  const filterChipsWrap = document.getElementById('filter-chips');
  const sortSelect = document.getElementById('sort-select');

  const outfitModal = document.getElementById('outfit-modal');
  const outfitModalBody = document.getElementById('outfit-modal-body');
  const addModal = document.getElementById('add-modal');
  const addModalTitle = document.getElementById('add-modal-title');
  const outfitForm = document.getElementById('outfit-form');
  const outfitIdField = document.getElementById('outfit-id-field');
  const outfitTitleInput = document.getElementById('outfit-title-input');
  const outfitDescInput = document.getElementById('outfit-desc-input');
  const outfitOccasionSelect = document.getElementById('outfit-occasion-select');
  const outfitSeasonSelect = document.getElementById('outfit-season-select');
  const outfitToneSelect = document.getElementById('outfit-tone-select');
  const outfitItemsInput = document.getElementById('outfit-items-input');
  const outfitAuthorInput = document.getElementById('outfit-author-input');
  const outfitFormSubmitBtn = document.getElementById('outfit-form-submit-btn');

  const imageDropZone = document.getElementById('image-drop-zone');
  const imageFileInput = document.getElementById('image-file-input');
  const imagePickerPlaceholder = document.getElementById('image-picker-placeholder');
  const imagePreview = document.getElementById('image-preview');
  const imageRemoveBtn = document.getElementById('image-remove-btn');

  const openAddModalBtn = document.getElementById('open-add-modal-btn');

  // ---------- Color palette UI ----------
  const paletteSuggestions = document.getElementById('palette-suggestions');
  const selectedColorsRow = document.getElementById('selected-colors-row');
  const noColorHint = document.getElementById('no-color-hint');
  const customColorInput = document.getElementById('custom-color-input');

  function populatePalette(tone) {
    if (!paletteSuggestions) return;
    const colors = PALETTE_BY_TONE[tone] || PALETTE_BY_TONE['뉴트럴'];
    paletteSuggestions.innerHTML = colors.map(function (c) {
      const isSelected = selectedColors.includes(c.hex);
      const isDark = isDarkColor(c.hex);
      return (
        '<button type="button" class="color-swatch-btn" data-hex="' + c.hex + '" title="' + c.name + '" ' +
        'style="width:2.2rem;height:2.2rem;border-radius:50%;background:' + c.hex + ';border:2px solid ' +
        (isSelected ? '#e879f9' : 'rgba(255,255,255,0.15)') + ';' +
        'box-shadow:' + (isSelected ? '0 0 0 3px rgba(232,121,249,0.4)' : 'none') + ';' +
        'cursor:pointer;position:relative;transition:transform .15s,box-shadow .15s,border-color .15s;flex-shrink:0;">' +
        (isSelected ? '<i class="fa-solid fa-check" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:0.65rem;color:' + (isDark ? '#fff' : '#1a0b2e') + ';pointer-events:none;"></i>' : '') +
        '</button>'
      );
    }).join('');

    paletteSuggestions.querySelectorAll('.color-swatch-btn').forEach(function (btn) {
      btn.addEventListener('click', function () { toggleColor(btn.dataset.hex, tone); });
      btn.addEventListener('mouseenter', function () { if (!selectedColors.includes(btn.dataset.hex)) btn.style.transform = 'scale(1.18)'; });
      btn.addEventListener('mouseleave', function () { btn.style.transform = 'scale(1)'; });
    });
  }

  function isDarkColor(hex) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return (r * 299 + g * 587 + b * 114) / 1000 < 128;
  }

  function toggleColor(hex, tone) {
    const idx = selectedColors.indexOf(hex);
    if (idx !== -1) {
      selectedColors.splice(idx, 1);
    } else {
      if (selectedColors.length >= 6) {
        selectedColors.shift();
      }
      selectedColors.push(hex);
    }
    populatePalette(tone || outfitToneSelect.value);
    renderSelectedColorsRow();
  }

  function renderSelectedColorsRow(fromPhoto) {
    if (!selectedColorsRow) return;
    if (!selectedColors.length) {
      selectedColorsRow.innerHTML = '<span id="no-color-hint" class="text-xs text-white/30">위에서 색상을 선택하세요</span>';
      return;
    }
    const badge = fromPhoto
      ? '<span style="display:inline-flex;align-items:center;gap:0.3rem;background:rgba(217,70,239,0.15);border:1px solid rgba(217,70,239,0.35);border-radius:999px;padding:0.2rem 0.6rem;font-size:0.7rem;color:#e879f9;white-space:nowrap;"><i class="fa-solid fa-camera" style="font-size:0.6rem;"></i>사진에서 추출</span>'
      : '';
    selectedColorsRow.innerHTML = badge + selectedColors.map(function (hex) {
      return (
        '<button type="button" data-hex="' + hex + '" title="제거" ' +
        'style="width:1.6rem;height:1.6rem;border-radius:50%;background:' + hex + ';' +
        'border:2px solid rgba(255,255,255,0.25);cursor:pointer;position:relative;flex-shrink:0;' +
        'transition:transform .15s;" ' +
        'class="selected-color-dot">' +
        '<i class="fa-solid fa-xmark" style="position:absolute;inset:0;display:none;align-items:center;justify-content:center;font-size:0.55rem;color:' + (isDarkColor(hex) ? '#fff' : '#1a0b2e') + ';"></i>' +
        '</button>'
      );
    }).join('') +
    '<span class="text-xs text-white/30 ml-1">' + selectedColors.length + '/6</span>';

    selectedColorsRow.querySelectorAll('.selected-color-dot').forEach(function (dot) {
      dot.addEventListener('click', function () {
        selectedColors = selectedColors.filter(function (h) { return h !== dot.dataset.hex; });
        populatePalette(outfitToneSelect ? outfitToneSelect.value : '뉴트럴');
        renderSelectedColorsRow();
      });
      dot.addEventListener('mouseenter', function () {
        dot.style.transform = 'scale(1.2)';
        dot.querySelector('i').style.display = 'flex';
      });
      dot.addEventListener('mouseleave', function () {
        dot.style.transform = 'scale(1)';
        dot.querySelector('i').style.display = 'none';
      });
    });
  }

  if (outfitToneSelect) {
    outfitToneSelect.addEventListener('change', function () {
      selectedColors = [];
      populatePalette(outfitToneSelect.value);
      renderSelectedColorsRow();
    });
  }

  if (customColorInput) {
    customColorInput.parentElement.addEventListener('click', function () {
      customColorInput.click();
    });
    customColorInput.addEventListener('input', function () {
      const hex = customColorInput.value;
      if (!selectedColors.includes(hex)) {
        if (selectedColors.length >= 6) selectedColors.shift();
        selectedColors.push(hex);
        renderSelectedColorsRow();
      }
    });
  }

  // ---------- localStorage helpers ----------
  function loadFromStorage() {
    try {
      allOutfits = JSON.parse(localStorage.getItem('aicodi_outfits') || '[]');
      allRatings = JSON.parse(localStorage.getItem('aicodi_ratings') || '[]');
    } catch (e) {
      allOutfits = [];
      allRatings = [];
    }
  }

  function saveOutfits() {
    localStorage.setItem('aicodi_outfits', JSON.stringify(allOutfits));
  }

  function saveRatings() {
    localStorage.setItem('aicodi_ratings', JSON.stringify(allRatings));
  }

  function generateId() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  }

  // ---------- Helpers ----------
  function escapeHtml(str) {
    if (str === undefined || str === null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function starsHtml(rating, size) {
    const r = Math.round(rating || 0);
    let html = '<span class="' + (size || 'star-display') + '">';
    for (let i = 1; i <= 5; i++) {
      html += '<i class="fa-solid fa-star" style="color:' + (i <= r ? '#fbbf24' : 'rgba(255,255,255,0.2)') + '"></i>';
    }
    html += '</span>';
    return html;
  }

  function getRatingsFor(outfitId) {
    return allRatings.filter(function (r) { return r.outfit_id === outfitId; });
  }

  function getAvgRating(outfitId) {
    const list = getRatingsFor(outfitId);
    if (!list.length) return 0;
    const sum = list.reduce(function (acc, r) { return acc + Number(r.rating || 0); }, 0);
    return sum / list.length;
  }

  function timeAgo(ts) {
    if (!ts) return '';
    const diff = Date.now() - Number(ts);
    const min = Math.floor(diff / 60000);
    if (min < 1) return '방금 전';
    if (min < 60) return min + '분 전';
    const hr = Math.floor(min / 60);
    if (hr < 24) return hr + '시간 전';
    const day = Math.floor(hr / 24);
    if (day < 30) return day + '일 전';
    return new Date(Number(ts)).toLocaleDateString('ko-KR');
  }

  // ---------- Data loading ----------
  function loadGalleryData() {
    galleryLoading.classList.remove('hidden');
    galleryEmpty.classList.add('hidden');
    loadFromStorage();
    galleryLoading.classList.add('hidden');
    renderStats();
    renderGallery();
  }

  function renderStats() {
    statOutfitCount.textContent = allOutfits.length;
    statReviewCount.textContent = allRatings.length;
    if (allRatings.length) {
      const sum = allRatings.reduce(function (acc, r) { return acc + Number(r.rating || 0); }, 0);
      statAvgRating.textContent = (sum / allRatings.length).toFixed(1);
    } else {
      statAvgRating.textContent = '-';
    }
  }

  // ---------- Rendering gallery grid ----------
  function renderGallery() {
    let list = allOutfits.slice();

    if (currentFilter !== '전체') {
      list = list.filter(function (o) { return o.occasion === currentFilter; });
    }

    if (currentSort === 'rating') {
      list.sort(function (a, b) { return getAvgRating(b.id) - getAvgRating(a.id); });
    } else if (currentSort === 'reviews') {
      list.sort(function (a, b) { return getRatingsFor(b.id).length - getRatingsFor(a.id).length; });
    } else {
      list.sort(function (a, b) { return (Number(b.created_at) || 0) - (Number(a.created_at) || 0); });
    }

    if (!list.length) {
      galleryGrid.innerHTML = '';
      galleryEmpty.classList.remove('hidden');
      return;
    }
    galleryEmpty.classList.add('hidden');

    galleryGrid.innerHTML = list.map(function (o) {
      const avg = getAvgRating(o.id);
      const reviewCount = getRatingsFor(o.id).length;
      const colors = Array.isArray(o.colors) ? o.colors : [];
      const colorDots = colors.slice(0, 5).map(function (c) {
        return '<span class="color-dot" style="background:' + escapeHtml(c) + '"></span>';
      }).join('');

      const imageHtml = o.image_url
        ? '<img src="' + escapeHtml(o.image_url) + '" alt="' + escapeHtml(o.title) + ' 코디 사진">'
        : '<div class="no-image-icon"><i class="fa-solid fa-' + escapeHtml(o.icon || 'shirt') + '"></i></div>';

      return (
        '<article class="outfit-card reveal visible" data-id="' + escapeHtml(o.id) + '">' +
          '<div class="outfit-card-image-wrap">' +
            imageHtml +
            (o.occasion ? '<span class="outfit-card-tag">' + escapeHtml(o.occasion) + '</span>' : '') +
          '</div>' +
          '<div class="outfit-card-body">' +
            '<h3 class="outfit-card-title">' + escapeHtml(o.title || '이름 없는 코디') + '</h3>' +
            '<p class="outfit-card-desc">' + escapeHtml(o.description || '설명이 없습니다.') + '</p>' +
            '<div class="outfit-card-footer">' +
              '<div class="flex items-center gap-1.5">' + starsHtml(avg) + '<span class="text-white/40 text-xs">(' + reviewCount + ')</span></div>' +
              '<div class="flex items-center gap-1">' + colorDots + '</div>' +
            '</div>' +
            '<div class="mt-3 text-xs text-white/40"><i class="fa-solid fa-user mr-1"></i>' + escapeHtml(o.author || '익명') + '</div>' +
          '</div>' +
        '</article>'
      );
    }).join('');
  }

  // ---------- Filter & sort listeners ----------
  if (filterChipsWrap) {
    filterChipsWrap.addEventListener('click', function (e) {
      const btn = e.target.closest('.filter-chip');
      if (!btn) return;
      filterChipsWrap.querySelectorAll('.filter-chip').forEach(function (c) { c.classList.remove('active'); });
      btn.classList.add('active');
      currentFilter = btn.dataset.occasion;
      renderGallery();
    });
  }

  if (sortSelect) {
    sortSelect.addEventListener('change', function () {
      currentSort = sortSelect.value;
      renderGallery();
    });
  }

  // ---------- Detail modal ----------
  function openOutfitModal(id) {
    const outfit = allOutfits.find(function (o) { return o.id === id; });
    if (!outfit) return;
    currentDetailOutfitId = id;
    renderOutfitModalBody(outfit);
    outfitModal.classList.add('show');
    document.body.style.overflow = 'hidden';
  }

  function closeOutfitModal() {
    outfitModal.classList.remove('show');
    document.body.style.overflow = '';
    currentDetailOutfitId = null;
    selectedRatingValue = 0;
  }

  function renderOutfitModalBody(outfit) {
    const ratingsList = getRatingsFor(outfit.id).sort(function (a, b) { return (Number(b.created_at) || 0) - (Number(a.created_at) || 0); });
    const avg = getAvgRating(outfit.id);
    const items = Array.isArray(outfit.items) ? outfit.items : [];
    const colors = Array.isArray(outfit.colors) ? outfit.colors : [];

    const imageHtml = outfit.image_url
      ? '<img src="' + escapeHtml(outfit.image_url) + '" alt="' + escapeHtml(outfit.title) + ' 코디 사진">'
      : '<div class="no-image-icon"><i class="fa-solid fa-' + escapeHtml(outfit.icon || 'shirt') + '"></i></div>';

    const itemsHtml = items.length
      ? items.map(function (it) { return '<span class="modal-tag" style="margin-bottom:0.4rem;">' + escapeHtml(it) + '</span>'; }).join('')
      : '<span class="text-white/40 text-sm">등록된 아이템이 없습니다.</span>';

    const colorsHtml = colors.length
      ? colors.map(function (c) { return '<span class="color-dot" style="width:1.4rem;height:1.4rem;background:' + escapeHtml(c) + '"></span>'; }).join('')
      : '<span class="text-white/40 text-sm">등록된 컬러가 없습니다.</span>';

    const reviewsHtml = ratingsList.length
      ? ratingsList.map(function (r) {
          return (
            '<div class="review-item">' +
              '<div class="flex items-center justify-between mb-1.5">' +
                '<span class="font-semibold text-sm">' + escapeHtml(r.reviewer || '익명') + '</span>' +
                starsHtml(r.rating, 'star-display') +
              '</div>' +
              (r.comment ? '<p class="text-sm text-white/60 leading-relaxed">' + escapeHtml(r.comment) + '</p>' : '') +
              (r.created_at ? '<p class="text-xs text-white/30 mt-1">' + timeAgo(r.created_at) + '</p>' : '') +
            '</div>'
          );
        }).join('')
      : '<p class="text-sm text-white/40 py-4">아직 리뷰가 없어요. 첫 리뷰를 남겨보세요!</p>';

    outfitModalBody.innerHTML =
      '<div class="modal-image-wrap">' + imageHtml + '</div>' +
      '<div class="flex flex-wrap items-center gap-2 mb-3">' +
        (outfit.occasion ? '<span class="modal-tag">' + escapeHtml(outfit.occasion) + '</span>' : '') +
        (outfit.season ? '<span class="modal-tag">' + escapeHtml(outfit.season) + '</span>' : '') +
        (outfit.tone ? '<span class="modal-tag">' + escapeHtml(outfit.tone) + '</span>' : '') +
      '</div>' +
      '<h3 class="font-display font-bold text-2xl mb-2">' + escapeHtml(outfit.title || '') + '</h3>' +
      '<div class="flex items-center gap-2 mb-4 text-sm text-white/50">' +
        '<i class="fa-solid fa-user"></i>' + escapeHtml(outfit.author || '익명') +
        '<span class="w-1 h-1 rounded-full bg-white/30"></span>' +
        starsHtml(avg) + '<span>' + (avg ? avg.toFixed(1) : '0.0') + ' (' + ratingsList.length + '개 리뷰)</span>' +
      '</div>' +
      '<p class="text-white/65 text-sm leading-relaxed mb-6">' + escapeHtml(outfit.description || '설명이 없습니다.') + '</p>' +
      '<div class="mb-6">' +
        '<h4 class="form-label">구성 아이템</h4>' +
        '<div class="flex flex-wrap gap-2">' + itemsHtml + '</div>' +
      '</div>' +
      '<div class="mb-6">' +
        '<h4 class="form-label">컬러 팔레트</h4>' +
        '<div class="flex flex-wrap gap-2">' + colorsHtml + '</div>' +
      '</div>' +
      '<div class="mb-6">' +
        '<button type="button" id="modal-edit-btn" class="owner-action-btn"><i class="fa-solid fa-pen"></i> 코디 수정하기</button>' +
      '</div>' +
      '<div class="border-t border-white/10 pt-6">' +
        '<h4 class="font-semibold text-lg mb-5"><i class="fa-solid fa-star text-amber-400 mr-1"></i>별점 남기기</h4>' +
        '<form id="rating-form" class="space-y-4">' +
          '<div class="flex flex-col items-center gap-2 py-2">' +
            '<div class="star-input" id="rating-star-input">' +
              [1,2,3,4,5].map(function(n){ return '<i class="fa-solid fa-star" data-value="'+n+'"></i>'; }).join('') +
            '</div>' +
            '<span id="rating-label" style="font-size:0.82rem;color:rgba(255,255,255,0.35);min-height:1.2em;transition:color .2s;">별을 클릭해 점수를 선택하세요</span>' +
          '</div>' +
          '<div class="grid grid-cols-2 gap-3">' +
            '<input type="text" id="rating-reviewer-input" class="form-input" placeholder="닉네임" maxlength="20">' +
            '<div></div>' +
          '</div>' +
          '<textarea id="rating-comment-input" class="form-input" rows="2" placeholder="이 코디에 대한 한줄 코멘트 (선택)" maxlength="200"></textarea>' +
          '<p id="rating-error" class="hidden text-xs text-rose-400 flex items-center gap-1"><i class="fa-solid fa-circle-exclamation"></i><span id="rating-error-text"></span></p>' +
          '<button type="submit" id="rating-submit-btn" class="form-submit-btn"><i class="fa-solid fa-paper-plane"></i> 별점 등록하기</button>' +
          '<div id="rating-success" class="hidden flex-col items-center gap-2 py-4 text-center">' +
            '<i class="fa-solid fa-circle-check text-emerald-400 text-3xl"></i>' +
            '<p class="font-semibold text-emerald-300">별점이 등록되었어요!</p>' +
            '<p class="text-xs text-white/40">소중한 리뷰 감사합니다 :)</p>' +
          '</div>' +
        '</form>' +
      '</div>' +
      '<div class="border-t border-white/10 pt-6 mt-6">' +
        '<h4 class="font-semibold text-lg mb-2">리뷰 (' + ratingsList.length + ')</h4>' +
        reviewsHtml +
      '</div>';

    selectedRatingValue = 0;
    const starWrap = document.getElementById('rating-star-input');
    const ratingLabel = document.getElementById('rating-label');
    const RATING_LABELS = ['', '최악이에요 😞', '별로예요 😕', '보통이에요 😊', '좋아요! 😍', '최고예요! 🤩'];

    if (starWrap) {
      const stars = Array.from(starWrap.querySelectorAll('i'));

      function paintStars(upTo, isHover) {
        stars.forEach(function (s) {
          const v = Number(s.dataset.value);
          if (v <= upTo) {
            s.style.color = isHover ? '#fcd34d' : '#fbbf24';
            s.style.filter = isHover ? 'none' : 'drop-shadow(0 0 6px rgba(251,191,36,0.5))';
            s.style.transform = isHover ? 'scale(1.18)' : 'scale(1.1)';
          } else {
            s.style.color = 'rgba(255,255,255,0.15)';
            s.style.filter = 'none';
            s.style.transform = 'scale(1)';
          }
        });
      }

      starWrap.addEventListener('mouseleave', function () {
        paintStars(selectedRatingValue, false);
        if (ratingLabel) {
          ratingLabel.textContent = selectedRatingValue ? RATING_LABELS[selectedRatingValue] : '별을 클릭해 점수를 선택하세요';
          ratingLabel.style.color = selectedRatingValue ? '#fbbf24' : 'rgba(255,255,255,0.35)';
        }
      });

      stars.forEach(function (star) {
        star.addEventListener('mouseenter', function () {
          const v = Number(star.dataset.value);
          paintStars(v, true);
          if (ratingLabel) {
            ratingLabel.textContent = RATING_LABELS[v];
            ratingLabel.style.color = '#fcd34d';
          }
        });

        star.addEventListener('click', function () {
          selectedRatingValue = Number(star.dataset.value);
          paintStars(selectedRatingValue, false);
          if (ratingLabel) {
            ratingLabel.textContent = RATING_LABELS[selectedRatingValue];
            ratingLabel.style.color = '#fbbf24';
          }
          star.classList.add('bounce');
          setTimeout(function () { star.classList.remove('bounce'); }, 400);
        });
      });
    }

    const ratingForm = document.getElementById('rating-form');
    if (ratingForm) {
      ratingForm.addEventListener('submit', function (e) {
        e.preventDefault();
        submitRating(outfit.id);
      });
    }

    const editBtn = document.getElementById('modal-edit-btn');
    if (editBtn) {
      editBtn.addEventListener('click', function () {
        closeOutfitModal();
        openEditModal(outfit.id);
      });
    }
  }

  function submitRating(outfitId) {
    const reviewerInput = document.getElementById('rating-reviewer-input');
    const commentInput = document.getElementById('rating-comment-input');
    const errorEl = document.getElementById('rating-error');
    const errorText = document.getElementById('rating-error-text');
    const submitBtn = document.getElementById('rating-submit-btn');
    const successEl = document.getElementById('rating-success');

    function showError(msg) {
      if (errorEl) { errorEl.classList.remove('hidden'); }
      if (errorText) { errorText.textContent = msg; }
    }
    function clearError() {
      if (errorEl) { errorEl.classList.add('hidden'); }
    }

    clearError();

    const reviewer = reviewerInput ? reviewerInput.value.trim() : '';

    if (!selectedRatingValue) {
      showError('별을 클릭해 점수를 선택해주세요.');
      return;
    }
    if (!reviewer) {
      showError('닉네임을 입력해주세요.');
      if (reviewerInput) reviewerInput.focus();
      return;
    }

    // 로딩 상태
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> 등록 중...';
    }

    const newRating = {
      id: generateId(),
      outfit_id: outfitId,
      rating: selectedRatingValue,
      reviewer: reviewer,
      comment: commentInput ? commentInput.value.trim() : '',
      created_at: Date.now()
    };

    allRatings.push(newRating);
    saveRatings();

    // 성공 UI
    if (submitBtn) submitBtn.style.display = 'none';
    if (successEl) {
      successEl.classList.remove('hidden');
      successEl.style.display = 'flex';
    }

    // 1.5초 후 리뷰 목록 갱신
    setTimeout(function () {
      renderStats();
      const outfit = allOutfits.find(function (o) { return o.id === outfitId; });
      if (outfit) renderOutfitModalBody(outfit);
    }, 1500);
  }

  // ---------- Add / Edit modal ----------
  function resetOutfitForm() {
    outfitForm.reset();
    outfitIdField.value = '';
    editingOutfitId = null;
    pendingImageDataUrl = null;
    imagePreview.src = '';
    imagePreview.classList.add('hidden');
    imagePickerPlaceholder.classList.remove('hidden');
    imageRemoveBtn.classList.add('hidden');
    selectedColors = [];
    populatePalette('웜톤');
    renderSelectedColorsRow();
  }

  function openAddModal() {
    resetOutfitForm();
    addModalTitle.innerHTML = '<i class="fa-solid fa-camera-retro text-fuchsia-300 mr-2"></i>내 코디 등록하기';
    outfitFormSubmitBtn.innerHTML = '<i class="fa-solid fa-check"></i> 코디 등록하기';
    addModal.classList.add('show');
    document.body.style.overflow = 'hidden';
  }

  function openEditModal(id) {
    const outfit = allOutfits.find(function (o) { return o.id === id; });
    if (!outfit) return;
    resetOutfitForm();
    editingOutfitId = id;
    outfitIdField.value = id;
    outfitTitleInput.value = outfit.title || '';
    outfitDescInput.value = outfit.description || '';
    outfitOccasionSelect.value = outfit.occasion || '데일리';
    outfitSeasonSelect.value = outfit.season || '사계절';
    outfitToneSelect.value = outfit.tone || '뉴트럴';
    outfitItemsInput.value = Array.isArray(outfit.items) ? outfit.items.join(', ') : '';
    outfitAuthorInput.value = outfit.author || '';

    if (outfit.image_url) {
      pendingImageDataUrl = outfit.image_url;
      imagePreview.src = outfit.image_url;
      imagePreview.classList.remove('hidden');
      imagePickerPlaceholder.classList.add('hidden');
      imageRemoveBtn.classList.remove('hidden');
    }

    selectedColors = Array.isArray(outfit.colors) ? outfit.colors.slice() : [];
    populatePalette(outfit.tone || '뉴트럴');
    renderSelectedColorsRow();

    addModalTitle.innerHTML = '<i class="fa-solid fa-pen text-fuchsia-300 mr-2"></i>코디 수정하기';
    outfitFormSubmitBtn.innerHTML = '<i class="fa-solid fa-check"></i> 수정 완료';
    addModal.classList.add('show');
    document.body.style.overflow = 'hidden';
  }

  function closeAddModal() {
    addModal.classList.remove('show');
    document.body.style.overflow = '';
  }

  if (openAddModalBtn) {
    openAddModalBtn.addEventListener('click', openAddModal);
  }

  document.querySelectorAll('[data-close-modal]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      const targetId = btn.dataset.closeModal;
      if (targetId === 'outfit-modal') closeOutfitModal();
      if (targetId === 'add-modal') closeAddModal();
    });
  });

  [outfitModal, addModal].forEach(function (overlay) {
    if (!overlay) return;
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) {
        if (overlay === outfitModal) closeOutfitModal();
        if (overlay === addModal) closeAddModal();
      }
    });
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      closeOutfitModal();
      closeAddModal();
    }
  });

  if (galleryGrid) {
    galleryGrid.addEventListener('click', function (e) {
      const card = e.target.closest('.outfit-card');
      if (!card) return;
      openOutfitModal(card.dataset.id);
    });
  }

  // ---------- Image upload / resize ----------
  function resizeImageFile(file) {
    return new Promise(function (resolve, reject) {
      const reader = new FileReader();
      reader.onload = function (e) {
        const img = new Image();
        img.onload = function () {
          const maxSize = 900;
          let w = img.width;
          let h = img.height;
          if (w > maxSize || h > maxSize) {
            if (w > h) {
              h = Math.round(h * (maxSize / w));
              w = maxSize;
            } else {
              w = Math.round(w * (maxSize / h));
              h = maxSize;
            }
          }
          const canvas = document.createElement('canvas');
          canvas.width = w;
          canvas.height = h;
          const ctx = canvas.getContext('2d');
          ctx.drawImage(img, 0, 0, w, h);
          resolve(canvas.toDataURL('image/jpeg', 0.82));
        };
        img.onerror = reject;
        img.src = e.target.result;
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  // ---------- 사진 → 컬러 자동 추출 ----------
  function extractColorsFromDataUrl(dataUrl) {
    return new Promise(function (resolve) {
      const img = new Image();
      img.onload = function () {
        const SIZE = 120;
        const canvas = document.createElement('canvas');
        canvas.width = SIZE;
        canvas.height = SIZE;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, SIZE, SIZE);
        const data = ctx.getImageData(0, 0, SIZE, SIZE).data;

        // 픽셀 샘플링 + 양자화(step=24)
        const STEP = 24;
        const map = {};
        for (let i = 0; i < data.length; i += 4 * 4) {
          const a = data[i + 3];
          if (a < 200) continue;
          const r = Math.round(data[i]     / STEP) * STEP;
          const g = Math.round(data[i + 1] / STEP) * STEP;
          const b = Math.round(data[i + 2] / STEP) * STEP;
          const key = r + '|' + g + '|' + b;
          map[key] = (map[key] || 0) + 1;
        }

        // 빈도 내림차순 정렬
        const sorted = Object.entries(map)
          .sort(function (a, b) { return b[1] - a[1]; })
          .map(function (e) {
            const p = e[0].split('|').map(Number);
            return { r: p[0], g: p[1], b: p[2], n: e[1] };
          });

        // 색상 거리로 중복 제거 → 상위 6색
        const picked = [];
        for (let i = 0; i < sorted.length && picked.length < 6; i++) {
          const c = sorted[i];
          const tooClose = picked.some(function (p) {
            return Math.abs(c.r - p.r) + Math.abs(c.g - p.g) + Math.abs(c.b - p.b) < 72;
          });
          if (!tooClose) picked.push(c);
        }

        const hexList = picked.map(function (c) {
          return '#' +
            Math.min(255, c.r).toString(16).padStart(2, '0') +
            Math.min(255, c.g).toString(16).padStart(2, '0') +
            Math.min(255, c.b).toString(16).padStart(2, '0');
        });
        resolve(hexList);
      };
      img.onerror = function () { resolve([]); };
      img.src = dataUrl;
    });
  }

  function showPaletteLoading() {
    if (!selectedColorsRow) return;
    selectedColorsRow.innerHTML =
      '<i class="fa-solid fa-circle-notch fa-spin text-fuchsia-300 text-xs mr-1"></i>' +
      '<span class="text-xs text-white/50">사진에서 색상 추출 중...</span>';
  }

  async function handleImageFile(file) {
    if (!file || !file.type.startsWith('image/')) {
      alert('이미지 파일만 업로드할 수 있어요.');
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      alert('이미지 용량은 8MB 이하로 업로드해주세요.');
      return;
    }
    try {
      const dataUrl = await resizeImageFile(file);
      pendingImageDataUrl = dataUrl;
      imagePreview.src = dataUrl;
      imagePreview.classList.remove('hidden');
      imagePickerPlaceholder.classList.add('hidden');
      imageRemoveBtn.classList.remove('hidden');

      // 컬러 자동 추출
      showPaletteLoading();
      const extracted = await extractColorsFromDataUrl(dataUrl);
      if (extracted.length) {
        selectedColors = extracted;
        populatePalette(outfitToneSelect ? outfitToneSelect.value : '뉴트럴');
        renderSelectedColorsRow(true);
      }
    } catch (err) {
      console.error('이미지 처리 실패:', err);
      alert('이미지를 처리하는 중 오류가 발생했습니다.');
    }
  }

  if (imageDropZone) {
    imageDropZone.addEventListener('click', function (e) {
      if (e.target === imageRemoveBtn || imageRemoveBtn.contains(e.target)) return;
      imageFileInput.click();
    });

    imageDropZone.addEventListener('dragover', function (e) {
      e.preventDefault();
      imageDropZone.classList.add('drag-over');
    });

    imageDropZone.addEventListener('dragleave', function () {
      imageDropZone.classList.remove('drag-over');
    });

    imageDropZone.addEventListener('drop', function (e) {
      e.preventDefault();
      imageDropZone.classList.remove('drag-over');
      const file = e.dataTransfer.files && e.dataTransfer.files[0];
      if (file) handleImageFile(file);
    });
  }

  if (imageFileInput) {
    imageFileInput.addEventListener('change', function () {
      const file = imageFileInput.files && imageFileInput.files[0];
      if (file) handleImageFile(file);
    });
  }

  if (imageRemoveBtn) {
    imageRemoveBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      pendingImageDataUrl = null;
      imageFileInput.value = '';
      imagePreview.src = '';
      imagePreview.classList.add('hidden');
      imagePickerPlaceholder.classList.remove('hidden');
      imageRemoveBtn.classList.add('hidden');
    });
  }

  // ---------- Form submit (create / edit) ----------
  const ICONS_BY_OCCASION = {
    '데일리': 'shirt', '오피스': 'briefcase', '데이트': 'heart',
    '여행': 'plane', '파티': 'champagne-glasses', '운동': 'dumbbell'
  };

  function randomPaletteFor(tone) {
    const palettes = {
      '웜톤': ['#e8c39e', '#d98d5f', '#f4b183', '#c46b3a'],
      '쿨톤': ['#a3c4dc', '#5b7ea1', '#2f4a63', '#dcecf5'],
      '뉴트럴': ['#d9d2c5', '#8f8577', '#4f4a43', '#f0ede6']
    };
    return palettes[tone] || palettes['뉴트럴'];
  }

  if (outfitForm) {
    outfitForm.addEventListener('submit', function (e) {
      e.preventDefault();

      const title = outfitTitleInput.value.trim();
      const author = outfitAuthorInput.value.trim();
      if (!title) { alert('코디 이름을 입력해주세요.'); return; }
      if (!author) { alert('등록자 닉네임을 입력해주세요.'); return; }

      const occasion = outfitOccasionSelect.value;
      const tone = outfitToneSelect.value;
      const itemsRaw = outfitItemsInput.value.trim();
      const items = itemsRaw ? itemsRaw.split(',').map(function (s) { return s.trim(); }).filter(Boolean) : [];

      const payload = {
        title: title,
        description: outfitDescInput.value.trim(),
        occasion: occasion,
        season: outfitSeasonSelect.value,
        tone: tone,
        items: items,
        colors: selectedColors.length ? selectedColors : randomPaletteFor(tone),
        icon: ICONS_BY_OCCASION[occasion] || 'shirt',
        author: author,
        image_url: pendingImageDataUrl || ''
      };

      outfitFormSubmitBtn.disabled = true;
      const originalBtnHtml = outfitFormSubmitBtn.innerHTML;
      outfitFormSubmitBtn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> 저장 중...';

      try {
        if (editingOutfitId) {
          const idx = allOutfits.findIndex(function (o) { return o.id === editingOutfitId; });
          if (idx !== -1) {
            allOutfits[idx] = Object.assign({}, allOutfits[idx], payload);
          }
        } else {
          payload.id = generateId();
          payload.created_at = Date.now();
          allOutfits.push(payload);
        }
        saveOutfits();
        closeAddModal();
        loadGalleryData();
      } catch (err) {
        console.error('코디 저장 실패:', err);
        alert('코디를 저장하는 중 오류가 발생했습니다.');
      } finally {
        outfitFormSubmitBtn.disabled = false;
        outfitFormSubmitBtn.innerHTML = originalBtnHtml;
      }
    });
  }

  // ---------- Init ----------
  document.addEventListener('DOMContentLoaded', function () {
    if (galleryGrid) {
      loadGalleryData();
    }
  });

  if (document.readyState === 'interactive' || document.readyState === 'complete') {
    if (galleryGrid) loadGalleryData();
  }
})();
